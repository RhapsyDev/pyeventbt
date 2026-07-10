"""
strategy.py — Motor de señales principal de la estrategia ORB Advanced.

La clase ORBAdvancedStrategy implementa la lógica completa de la estrategia:
  1. Formación del rango ORB (N velas de breakout_timeframe)
  2. Detección de ruptura o retest
  3. Generación de SignalEvent con SL/TP calculados
  4. Gestión del trailing stop barra a barra (si TP_Trailing activo)
  5. Cierre EOD forzado

El método process_bar_event() es el que se registra en pyeventbt como
custom_signal_engine. Se llama en cada BarEvent de cualquier timeframe
registrado en la estrategia.
"""

import re
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional

from pyeventbt import BarEvent, SignalEvent, Modules, StrategyTimeframes
from pyeventbt.events.events import OrderType, SignalType
from pyeventbt.utils.utils import TerminalColors

from impl.strategies.orb_advanced.session_state import OrbSessionState
from impl.strategies.orb_advanced.state_manager import ORBStateManager
from impl.strategies.orb_advanced.sl_calculators import StopLossCalculator
from impl.strategies.orb_advanced.tp_calculators import TakeProfitCalculator, TP_Trailing
from impl.strategies.orb_advanced.entry_calculators import EntryCalculator


def _clean_symbol(s: str) -> str:
    """Elimina el sufijo '+' de los símbolos MT5 swap-free."""
    return s.rstrip("+")


def _fmt_time(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def log_prefix(session: str, ts: datetime, symbol: str) -> str:
    return f"[{session}] [{_fmt_time(ts)}] [{symbol}]:"


class ORBAdvancedStrategy:
    """
    Motor de señales de la estrategia ORB (Opening Range Breakout) Avanzada.

    Parámetros
    ----------
    strategy_id       : Identificador único de la estrategia en pyeventbt.
    symbols           : Lista de símbolos a operar (sin sufijos).
    sessions          : Configuración de sesiones (horario, festivos, etc.).
    session_end_hour  : Hora de cierre forzado EOD (hora broker).
    orb_base_timeframe: Timeframe de formación del rango (ej. FIVE_MIN).
    breakout_timeframe: Timeframe de detección de ruptura (ej. ONE_MIN).
    entry_calculator  : Instancia de EntryCalculator (BREAKOUT, RETEST_ORB, FVG_RETEST, ...).
    sl_calculator     : Instancia de StopLossCalculator (OPPOSITE_RANGE o MID_RANGE).
    tp_calculator     : Instancia de TakeProfitCalculator (TP_Fixed o TP_Trailing).
    rr_ratio          : R:R para TP fijo (ignorado si tp_calculator es TP_Trailing).
    state             : ORBStateManager compartido con los hooks.
    logger            : Logger de Python configurado en main.py.
    verbose_mode      : Si True, emite mensajes de debug adicionales.
    """

    def __init__(
        self,
        strategy_id: str,
        symbols: List[str],
        sessions: Dict[str, Dict[str, Any]],
        session_end_hour: time,
        orb_base_timeframe: StrategyTimeframes,
        breakout_timeframe: StrategyTimeframes,
        entry_calculator: EntryCalculator,
        sl_calculator: StopLossCalculator,
        tp_calculator: TakeProfitCalculator,
        rr_ratio: float,
        risk_pct: float,
        state: ORBStateManager,
        logger,
        verbose_mode: bool = False,
        utc_offset_hours: int = 3,
        is_backtest: bool = True,
    ):
        self.strategy_id       = strategy_id
        self.symbols           = symbols
        self.orb_base_timeframe  = orb_base_timeframe
        self.breakout_timeframe  = breakout_timeframe
        self.entry_calculator  = entry_calculator
        self.sl_calculator     = sl_calculator
        self.tp_calculator     = tp_calculator
        self.rr_ratio          = rr_ratio
        self.risk_pct          = risk_pct
        self.state             = state
        self.logger            = logger
        self.verbose_mode      = verbose_mode
        self._utc_offset       = timedelta(hours=utc_offset_hours)
        self._is_backtest      = is_backtest

        # BACKTEST: session config in broker time → convert to UTC
        # LIVE: keep as-is (MT5 timestamps already in broker time)
        if is_backtest:
            self.sessions_config = {}
            for name, conf in sessions.items():
                c = dict(conf)
                bt_start = c["start_time"]
                utc_start = (datetime.combine(datetime(2000, 1, 1), bt_start)
                             - self._utc_offset).time()
                c["start_time"] = utc_start
                self.sessions_config[name] = c
            self.session_end_hour = (
                datetime.combine(datetime(2000, 1, 1), session_end_hour)
                - self._utc_offset
            ).time()
        else:
            self.sessions_config = sessions
            self.session_end_hour = session_end_hour

        # Estado por símbolo × sesión (reiniciado cada día)
        self.strategy_state: Dict[str, Dict[str, OrbSessionState]] = {
            sym: {sn: OrbSessionState() for sn in self.sessions_config}
            for sym in self.symbols
        }
        self.last_eod_check_date: Optional[datetime] = None
        self._session_complete_logged: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # Métodos auxiliares privados
    # ─────────────────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        self.logger.info(msg)

    def _debug(self, msg: str):
        if self.verbose_mode:
            self.logger.debug(msg)

    @staticmethod
    def _timeframe_to_minutes(tf) -> int:
        s = tf.value if hasattr(tf, "value") else str(tf)
        m = re.match(r"(\d+)\s*(min|hour|day|week)", s)
        if not m:
            return 5
        val, unit = int(m.group(1)), m.group(2)
        if unit == "hour":  return val * 60
        if unit == "day":   return val * 1440
        if unit == "week":  return val * 10080
        return val

    def _get_current_price(
        self, symbol: str, modules: Modules, signal_type: SignalType
    ) -> Decimal:
        tick = modules.DATA_PROVIDER.get_latest_tick(symbol)
        if tick:
            return Decimal(str(tick["ask"])) if signal_type == SignalType.BUY else Decimal(str(tick["bid"]))
        return Decimal("0.0")

    def _calculate_atr(self, bar_ranges: list, period: int = 14) -> Decimal:
        """
        Calcula la volatilidad media como promedio de rangos H-L de las velas del ORB.
        Nota: es una aproximación al ATR (no incluye gaps entre cierres).
        Se usa únicamente para dimensionar el trailing stop.
        """
        if not bar_ranges:
            return Decimal("0")
        buf = bar_ranges[-period:] if len(bar_ranges) > period else bar_ranges
        return sum(buf) / Decimal(str(len(buf)))

    # ─────────────────────────────────────────────────────────────────────────
    # Gestión de día y EOD
    # ─────────────────────────────────────────────────────────────────────────

    def _reset_daily_state(self, current_date: datetime) -> bool:
        """Detecta cambio de día y reinicia el estado de todas las sesiones."""
        if not self.last_eod_check_date or self.last_eod_check_date.date() < current_date.date():
            self._log(f"[SYS] [{_fmt_time(current_date)}] [---]: New day {current_date.date()}")
            for sym in self.symbols:
                for sn in self.sessions_config:
                    self.strategy_state[sym][sn] = OrbSessionState()
            self.last_eod_check_date = current_date
            self._session_complete_logged = False
            self.state.summarized_sessions.clear()
            self.state.session_positions.clear()
            self.state.session_risk_pool.clear()
            return True
        return False

    def _close_eod_positions(self, current_datetime: datetime, modules: Modules):
        """Cierra todas las posiciones abiertas al llegar la hora EOD."""
        if current_datetime.time() < self.session_end_hour:
            return
        if (self.last_eod_check_date and
                self.last_eod_check_date.date() == current_datetime.date() and
                self.last_eod_check_date.time() >= self.session_end_hour):
            return  # Ya se procesó hoy
        for sym in self.symbols:
            positions = modules.PORTFOLIO.get_number_of_strategy_open_positions_by_symbol(sym)
            total = positions.get("TOTAL", 0)
            if total > 0:
                self._log(f"[EOD] [{_fmt_time(current_datetime)}] [{sym}]: Closing {total} position(s)")
                modules.EXECUTION_ENGINE.close_strategy_short_positions_by_symbol(sym)
                modules.EXECUTION_ENGINE.close_strategy_long_positions_by_symbol(sym)
        self.last_eod_check_date = current_datetime

    # ─────────────────────────────────────────────────────────────────────────
    # Trailing stop (solo activo si tp_calculator es TP_Trailing)
    # ─────────────────────────────────────────────────────────────────────────

    def _check_trailing_stops(self, current_datetime: datetime, modules: Modules, event: BarEvent):
        """Evalúa el trailing stop en cada barra para todas las posiciones activas."""
        if not isinstance(self.tp_calculator, TP_Trailing):
            return

        divisor   = Decimal(10 ** event.data.digits)
        bar_low   = Decimal(str(event.data.low))   / divisor
        bar_high  = Decimal(str(event.data.high))  / divisor
        bar_close = Decimal(str(event.data.close)) / divisor

        for sym in self.symbols:
            trail = self.state.trail_state.get(sym)
            if trail is None or not trail.get("active"):
                continue

            result = self.tp_calculator.check_and_update_trail(trail, bar_high, bar_low, bar_close)
            if result == "CLOSE":
                direction = trail["direction"]
                level     = trail["trail_level"]
                self._log(
                    f"[TRAIL] [{_fmt_time(current_datetime)}] [{sym}]: "
                    f"Trailing SL hit @ {level:.2f} — closing position"
                )
                if direction == SignalType.BUY:
                    modules.EXECUTION_ENGINE.close_strategy_long_positions_by_symbol(sym)
                else:
                    modules.EXECUTION_ENGINE.close_strategy_short_positions_by_symbol(sym)

    # ─────────────────────────────────────────────────────────────────────────
    # Método principal: process_bar_event
    # ─────────────────────────────────────────────────────────────────────────

    def process_bar_event(self, event: BarEvent, modules: Modules) -> List[SignalEvent]:
        """
        Procesador principal de barras. Registrado en pyeventbt como signal engine.

        Se llama en cada BarEvent de orb_base_timeframe y breakout_timeframe.
        Retorna una lista de SignalEvent (puede estar vacía).
        """
        signal_events: List[SignalEvent] = []
        symbol           = _clean_symbol(event.symbol)
        current_datetime = event.datetime

        # ── Gestión de día ──────────────────────────────────────────────────
        if self._reset_daily_state(current_datetime):
            self.state.days_tested += 1

        # Ignorar velas de días anteriores al último reset
        if self.last_eod_check_date and current_datetime.date() < self.last_eod_check_date.date():
            return []

        self._close_eod_positions(current_datetime, modules)
        self._check_trailing_stops(current_datetime, modules, event)

        # Solo procesar los timeframes registrados
        if event.timeframe not in [self.orb_base_timeframe, self.breakout_timeframe]:
            return []

        # ── Loop de sesiones ────────────────────────────────────────────────
        for session_name, session_conf in self.sessions_config.items():
            if not session_conf["enabled"]:
                continue

            self.state.current_session = session_name
            session_state = self.strategy_state[symbol][session_name]
            session_start = session_conf["start_time"]
            max_wait      = session_conf["max_wait_minutes"]
            orb_minutes   = self._timeframe_to_minutes(self.orb_base_timeframe)
            current_time  = current_datetime.time()

            window_end = (
                datetime.combine(current_datetime.date(), session_start)
                + timedelta(minutes=orb_minutes)
            ).time()

            is_first_bar_today = (
                session_state.last_day_processed is None
                or current_datetime.date() != session_state.last_day_processed.date()
            )

            # ── Verificación de mercado cerrado ─────────────────────────────
            weekday = current_datetime.date().weekday()
            is_closed = (
                weekday == 5
                or (weekday == 4 and current_time >= time(21, 0))
                or (weekday == 6 and current_time < time(22, 0))
            )
            if is_closed:
                if not session_state.market_closed_logged:
                    self._log(
                        f"{TerminalColors.WARNING}"
                        f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                        f"Market is closed{TerminalColors.ENDC}"
                    )
                    session_state.market_closed_logged = True
                continue

            # ── Verificación de festivos ─────────────────────────────────────
            today = current_datetime.date()
            if today in session_conf.get("holidays", []):
                if not session_state.session_open_logged:
                    self._log(
                        f"{TerminalColors.WARNING}"
                        f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                        f"Holiday — {session_name} session skipped{TerminalColors.ENDC}"
                    )
                    session_state.session_open_logged = True
                    self.state.skipped["holiday"][symbol] = (
                        self.state.skipped["holiday"].get(symbol, 0) + 1
                    )
                continue

            # ── Detección de inicio de sesión ────────────────────────────────
            if is_first_bar_today and not session_state.orb_accumulating and not session_state.orb_formed:
                if current_time < session_start:
                    if not session_state.waiting_logged:
                        self._log(
                            f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                            f"Waiting for {session_name} at {session_start.strftime('%H:%M')} UTC..."
                        )
                        session_state.waiting_logged = True
                    continue

                in_window = (
                    session_start <= current_time <= window_end
                    if session_start <= window_end
                    else (current_time >= session_start or current_time <= window_end)
                )

                if in_window:
                    if not session_state.session_open_logged:
                        if session_name not in self.state.session_risk_pool:
                            self.state.session_risk_pool[session_name] = {
                                "budget_pct": float(self.risk_pct),
                                "pending_symbols": set(self.symbols),
                            }
                        self._log(
                            f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                            f"{session_name} SESSION OPEN NOW!"
                        )
                        session_state.session_open_logged = True

                    session_state.session_start_time  = current_datetime
                    session_state.last_day_processed  = current_datetime

                    if event.timeframe == self.breakout_timeframe:
                        divisor = Decimal(10 ** event.data.digits)
                        session_state.orb_high       = Decimal(str(event.data.high)) / divisor
                        session_state.orb_low        = Decimal(str(event.data.low))  / divisor
                        session_state.orb_window_start = current_datetime
                        session_state.orb_accumulating = True
                        self._log(
                            f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                            f"Forming {orb_minutes}m ORB range..."
                        )
                else:
                    if not session_state.waiting_logged:
                        self._log(
                            f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                            f"Session start missed — first bar at {current_time.strftime('%H:%M')} "
                            f"is past ORB window ({session_start.strftime('%H:%M')}–{window_end.strftime('%H:%M')})"
                        )
                        session_state.waiting_logged = True
                    session_state.last_day_processed = current_datetime
                    session_state.breakout_attempted = True
                    continue

            # ── Fase de acumulación del rango ────────────────────────────────
            if session_state.orb_accumulating:
                elapsed = int((current_datetime - session_state.orb_window_start).total_seconds() / 60)

                if elapsed < orb_minutes:
                    if event.timeframe == self.breakout_timeframe:
                        divisor  = Decimal(10 ** event.data.digits)
                        bar_high = Decimal(str(event.data.high)) / divisor
                        bar_low  = Decimal(str(event.data.low))  / divisor
                        bar_close = Decimal(str(event.data.close)) / divisor
                        session_state.orb_high = max(session_state.orb_high, bar_high)
                        session_state.orb_low  = min(session_state.orb_low,  bar_low)
                        session_state.bar_ranges.append(bar_high - bar_low)
                        # -- Acumulacion para filtros volumen / VWAP --
                        tv = event.data.tickvol
                        session_state.orb_tickvols.append(tv)
                        session_state.orb_cumulative_tickvol += tv
                        session_state.orb_cumulative_pv += bar_close * Decimal(str(tv))
                    continue

                session_state.orb_accumulating = False
                session_state.orb_formed = True
                self._log(
                    f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                    f"{orb_minutes}m ORB formed | "
                    f"High={session_state.orb_high:.2f}  Low={session_state.orb_low:.2f} | "
                    f"Waiting for breakout..."
                )
                continue

            # ── ORB formado: timeout + breakout + retest ─────────────────────
            if session_state.orb_formed and not session_state.breakout_attempted:
                elapsed = (
                    int((current_datetime - session_state.session_start_time).total_seconds() / 60)
                    if session_state.session_start_time else 0
                )

                # Timeout
                if session_state.session_start_time and elapsed > max_wait:
                    if session_state.retest_mode:
                        self._log(
                            f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                            f"Retest timeout {elapsed} min | Session cancelled"
                        )
                        self.state.cancelled["timeout"][symbol] = (
                            self.state.cancelled["timeout"].get(symbol, 0) + 1
                        )
                    else:
                        self._log(
                            f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                            f"Timeout {elapsed} min | Session cancelled"
                        )
                        self.state.cancelled["expired"][symbol] = (
                            self.state.cancelled["expired"].get(symbol, 0) + 1
                        )
                    session_state.orb_formed        = False
                    session_state.breakout_attempted = True
                    continue

                # ── Breakout (timeframe rápido) ──────────────────────────────
                if event.timeframe == self.breakout_timeframe and not session_state.breakout_occurred:
                    divisor      = Decimal(10 ** event.data.digits)
                    current_close = Decimal(str(event.data.close)) / divisor
                    bar_high      = Decimal(str(event.data.high))  / divisor
                    bar_low       = Decimal(str(event.data.low))   / divisor
                    signal_type: Optional[SignalType] = None

                    if current_close > session_state.orb_high:
                        signal_type = SignalType.BUY
                        self._log(
                            f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                            f"Breakout BUY | Close {current_close:.2f} > ORB High {session_state.orb_high:.2f}"
                        )
                    elif current_close < session_state.orb_low:
                        signal_type = SignalType.SELL
                        self._log(
                            f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                            f"Breakout SELL | Close {current_close:.2f} < ORB Low {session_state.orb_low:.2f}"
                        )

                    if signal_type is not None:
                        session_state.breakout_occurred = True
                        session_state.breakout_high     = bar_high
                        session_state.breakout_low      = bar_low
                        session_state.breakout_bar_tickvol = event.data.tickvol
                        session_state.breakout_bar_range   = bar_high - bar_low

                        if self.entry_calculator.on_breakout(signal_type, event, session_state):
                            # Entrada inmediata
                            se = self._build_signal(
                                event, session_state, signal_type, session_name,
                                bar_high, bar_low, modules, current_datetime,
                            )
                            if se:
                                signal_events.append(se)
                                session_state.breakout_attempted = True
                        elif self.entry_calculator.supports_retest and self.entry_calculator.has_retest_setup(session_state):
                            # Modo retest (RETEST_ORB / FVG_RETEST)
                            session_state.retest_mode      = True
                            session_state.retest_direction = signal_type
                            session_state.retest_boundary  = (
                                session_state.orb_high if signal_type == SignalType.BUY
                                else session_state.orb_low
                            )
                            if session_state.fvg_high is not None:
                                self._log(
                                    f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                                    f"Waiting for FVG retest zone {session_state.fvg_low:.2f} - {session_state.fvg_high:.2f}..."
                                )
                            else:
                                self._log(
                                    f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                                    f"Waiting for retest at {session_state.retest_boundary:.2f}..."
                                )
                        else:
                            # Filtros de confirmacion rechazaron la entrada
                            self._debug(
                                f"[{session_name}] [{_fmt_time(current_datetime)}] [{symbol}]: "
                                f"Breakout {signal_type.name} rejected by entry filters"
                            )
                            session_state.breakout_attempted = True
                            self.state.cancelled["expired"][symbol] = (
                                self.state.cancelled["expired"].get(symbol, 0) + 1
                            )
                        continue

                    # ── No breakout this bar: track for FVG detection ────────
                    session_state.last_bar_high = bar_high
                    session_state.last_bar_low  = bar_low

                # ── Verificación de retest ───────────────────────────────────
                if session_state.retest_mode and not session_state.breakout_attempted:
                    if event.timeframe == self.breakout_timeframe:
                        retest_result = self.entry_calculator.on_bar(event, session_state)
                        if retest_result is not None:
                            entry_price, signal_type = retest_result
                            divisor  = Decimal(10 ** event.data.digits)
                            bar_high = Decimal(str(event.data.high)) / divisor
                            bar_low  = Decimal(str(event.data.low))  / divisor
                            session_state.breakout_attempted = True
                            session_state.retest_mode        = False

                            se = self._build_signal(
                                event, session_state, signal_type, session_name,
                                bar_high, bar_low, modules, current_datetime,
                                entry_override=entry_price,
                            )
                            if se:
                                signal_events.append(se)

        # ── Verificación de fin de sesiones ─────────────────────────────────
        if not self._session_complete_logged:
            all_done = all(
                self.strategy_state[sym][sn].breakout_attempted
                for sym in self.symbols
                for sn, sc in self.sessions_config.items()
                if sc["enabled"]
            )
            if all_done:
                self._session_complete_logged = True
                enabled = [sn for sn, sc in self.sessions_config.items() if sc["enabled"]]
                self._log(
                    f"[SYS] [{_fmt_time(current_datetime)}] [---]: "
                    f"All symbols completed for {'/'.join(enabled)} session(s). "
                    f"Waiting for next session/day..."
                )

        return signal_events

    # ─────────────────────────────────────────────────────────────────────────
    # Construcción de SignalEvent
    # ─────────────────────────────────────────────────────────────────────────

    def _build_signal(
        self,
        event: BarEvent,
        session_state: OrbSessionState,
        signal_type: SignalType,
        session_name: str,
        bar_high: Decimal,
        bar_low: Decimal,
        modules: Modules,
        current_datetime: datetime,
        entry_override: Optional[Decimal] = None,
    ) -> Optional[SignalEvent]:
        """
        Construye un SignalEvent con SL y TP calculados según los métodos configurados.
        Registra la señal en state.pending_signals para enlazarla con el FillEvent.
        Si el tp_calculator es TP_Trailing, inicializa el trail_state del símbolo.
        """
        symbol = _clean_symbol(event.symbol)

        entry_price = (
            entry_override
            if entry_override is not None
            else self._get_current_price(event.symbol, modules, signal_type)
        )

        atr_val  = self._calculate_atr(session_state.bar_ranges)
        sl_price = self.sl_calculator.calculate_sl(
            entry_price,
            session_state.orb_high,
            session_state.orb_low,
            signal_type,
            volatility=atr_val,
            bar_low=bar_low,
            bar_high=bar_high,
        )
        tp_price = self.tp_calculator.calculate_tp(entry_price, sl_price, self.rr_ratio, signal_type)

        signal_event = SignalEvent(
            symbol=event.symbol,
            time_generated=current_datetime,
            strategy_id=self.strategy_id,
            signal_type=signal_type,
            order_type=OrderType.MARKET,
            order_price=entry_price,
            sl=sl_price,
            tp=tp_price,
        )

        self.state.pending_signals = [
            s for s in self.state.pending_signals
            if _clean_symbol(s["symbol"]) != symbol
        ]
        self.state.pending_signals.append({
            "symbol":       event.symbol,
            "entry":        entry_price,
            "sl":           sl_price,
            "tp":           tp_price,
            "signal_type":  signal_type,
            "session":      session_name,
        })
        self.state.current_session_for_signal[symbol] = session_name

        # Si es trailing, inicializar el estado de trail
        if isinstance(self.tp_calculator, TP_Trailing):
            self.state.trail_state[symbol] = self.tp_calculator.init_trail_state(
                entry=entry_price,
                initial_sl=sl_price,
                atr=atr_val,
                direction=signal_type,
            )

        return signal_event
