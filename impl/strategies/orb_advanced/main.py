"""
main.py — Punto de entrada para la estrategia ORB Advanced.

Permite ejecutar la estrategia en modo BACKTEST o LIVE, aceptando parámetros
de configuración a través de argumentos de línea de comandos (argparse).
Esto facilita la ejecución de múltiples combinaciones desde el runner
sin necesidad de modificar el código fuente con expresiones regulares.

Uso:
  python strategies/orb_advanced/main.py --mode BACKTEST --entry BREAKOUT --sl OPPOSITE_RANGE --tp FIXED_1R
  python strategies/orb_advanced/main.py --mode LIVE
"""

import sys
import os
import argparse
import logging
from decimal import Decimal

# Aseguramos que el import path incluya la raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import MetaTrader5 as mt5

from pyeventbt import (
    Strategy,
    Modules,
    RiskPctSizingConfig,
    MinSizingConfig,
    Mt5PlatformConfig,
)
from pyeventbt.hooks.hook_service import Hooks
from pyeventbt.portfolio_handler.core.entities.suggested_order import SuggestedOrder
from pyeventbt.strategy.core.account_currencies import AccountCurrencies
from pyeventbt.events.events import SignalType
from pyeventbt.utils.utils import TerminalColors

# Imports del package orb_advanced
from impl.strategies.orb_advanced import config
from impl.strategies.orb_advanced.patches import (
    apply_symbol_info_patch,
    apply_commission_patch,
    apply_live_patches,
)
from impl.strategies.orb_advanced.sl_calculators import SL_OppositeRange, SL_MidRange
from impl.strategies.orb_advanced.tp_calculators import TP_Fixed, TP_Trailing
from impl.strategies.orb_advanced.entry_calculators import Entry_Breakout, Entry_Retest
from impl.strategies.orb_advanced.state_manager import ORBStateManager
from impl.strategies.orb_advanced.strategy import ORBAdvancedStrategy
from impl.strategies.orb_advanced.hooks import make_on_fill_hook, make_on_end_hook


def setup_logger(verbose: bool):
    """Configura el logger de pyeventbt con el formateador de color customizado."""
    class ResultColorFormatter(logging.Formatter):
        def format(self, record):
            msg = record.getMessage()
            if "TP reached:" in msg:
                msg = f"{TerminalColors.OKGREEN}{msg}{TerminalColors.ENDC}"
            elif "SL reached:" in msg:
                msg = f"{TerminalColors.FAIL}{msg}{TerminalColors.ENDC}"
            record.msg = msg
            return super().format(record)

    logger = logging.getLogger("pyeventbt")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(ResultColorFormatter(formatter._fmt))
    logger.addHandler(ch)

    return logger


def parse_args():
    parser = argparse.ArgumentParser(description="Run ORB Advanced Strategy")
    parser.add_argument("--mode", type=str, choices=["BACKTEST", "LIVE"],
                        help="Execution mode (BACKTEST or LIVE). Defaults to config.MODE.")
    parser.add_argument("--entry", type=str, choices=[e.value for e in config.EntryMethod],
                        help="Entry method. Defaults to config.ENTRY_METHOD.")
    parser.add_argument("--sl", type=str, choices=[e.value for e in config.SLMethod],
                        help="Stop Loss method. Defaults to config.SL_METHOD.")
    parser.add_argument("--tp", type=str, choices=[e.value for e in config.TPMethod],
                        help="Take Profit method. Defaults to config.TP_METHOD.")
    parser.add_argument("--rr", type=float,
                        help="Risk:Reward ratio for Fixed TP. Defaults to config.RR_RATIO.")
    parser.add_argument("--symbols", type=str,
                        help="Comma-separated list of symbols (e.g. XAUUSD,SP500). Defaults to config.SYMBOLS.")
    parser.add_argument("--start-date", type=str,
                        help="Start date for backtest (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str,
                        help="End date for backtest (YYYY-MM-DD)")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose debug logging.")
    return parser.parse_args()


def main():
    args = parse_args()

    # Sobreescribir configuración desde argparse
    if args.mode:
        config.MODE = args.mode
    if args.entry:
        config.ENTRY_METHOD = config.EntryMethod(args.entry)
    if args.sl:
        config.SL_METHOD = config.SLMethod(args.sl)
    if args.tp:
        config.TP_METHOD = config.TPMethod(args.tp)
    if args.rr is not None:
        config.RR_RATIO = args.rr
    if args.symbols:
        config.SYMBOLS = [s.strip() for s in args.symbols.split(",") if s.strip()]

    # Parsear fechas si vienen por CLI
    if args.start_date:
        from datetime import datetime
        dt = datetime.strptime(args.start_date, "%Y-%m-%d")
        config.BT_FROM = dt
        config.DATA_FROM = dt
    if args.end_date:
        from datetime import datetime
        dt = datetime.strptime(args.end_date, "%Y-%m-%d")
        config.BT_TO = dt
        config.DATA_TO = dt

    # Símbolos internos (limpios de sufijos MT5 en backtest, mapeados en live)
    if config.MODE == "LIVE":
        config.STRATEGY_SYMBOLS = [s.rstrip("+") for s in config.SYMBOLS]
        mt5_symbols = [config.MT5_SYMBOL_MAP.get(s, s) for s in config.SYMBOLS]
    else:
        config.STRATEGY_SYMBOLS = [s.rstrip("+") for s in config.SYMBOLS]
        mt5_symbols = config.STRATEGY_SYMBOLS  # No se usa en backtest, pero lo definimos

    logger = setup_logger(config.VERBOSE_MODE or args.verbose)
    state = ORBStateManager()

    logger.info(f"[SYS] [---] [---]: {config.MODE} mode activated | ENTRY={config.ENTRY_METHOD.value} SL={config.SL_METHOD.value} TP={config.TP_METHOD.value}")
    logger.info(f"[SYS] [---] [---]: Strategy symbols: {config.STRATEGY_SYMBOLS}")

    # =========================================================================
    # Inicialización de calculadores (Patrón Factory simple)
    # =========================================================================
    if config.ENTRY_METHOD == config.EntryMethod.BREAKOUT:
        entry_calc = Entry_Breakout()
    else:
        entry_calc = Entry_Retest()

    if config.SL_METHOD == config.SLMethod.OPPOSITE_RANGE:
        sl_calc = SL_OppositeRange()
    else:
        sl_calc = SL_MidRange()

    if config.TP_METHOD == config.TPMethod.FIXED_1R:
        tp_calc = TP_Fixed(rr=1.0)
    elif config.TP_METHOD == config.TPMethod.FIXED_1_5R:
        tp_calc = TP_Fixed(rr=1.5)
    else:
        tp_calc = TP_Trailing(
            atr_multiplier=config.TRAILING_ATR_MULTIPLIER,
            be_r=config.TRAILING_BE_R,
            activate_r=config.TRAILING_ACTIVATE_R
        )

    # =========================================================================
    # Configuración de Patches (Monkey-patching al framework)
    # =========================================================================
    if config.MODE == "BACKTEST":
        apply_symbol_info_patch()
    
    apply_commission_patch(config.BROKER)
    
    if config.MODE == "LIVE":
        apply_live_patches(state)

    # =========================================================================
    # Construcción de la Estrategia (PyEventBT Strategy)
    # =========================================================================
    s = Strategy(logging_level=logging.DEBUG if (config.VERBOSE_MODE or args.verbose) else logging.INFO)
    
    orb_strat = ORBAdvancedStrategy(
        strategy_id=config.STRATEGY_ID,
        symbols=config.STRATEGY_SYMBOLS,
        sessions=config.SESSIONS,
        session_end_hour=config.SESSION_END_HOUR,
        orb_base_timeframe=config.ORB_BASE_TIMEFRAME,
        breakout_timeframe=config.BREAKOUT_TIMEFRAME,
        entry_calculator=entry_calc,
        sl_calculator=sl_calc,
        tp_calculator=tp_calc,
        rr_ratio=config.RR_RATIO,
        state=state,
        logger=logger,
        verbose_mode=(config.VERBOSE_MODE or args.verbose)
    )

    # Custom signal engine (wrapper)
    def _signal_engine(event, modules):
        return orb_strat.process_bar_event(event, modules)

    s.custom_signal_engine(
        strategy_id=config.STRATEGY_ID,
        strategy_timeframes=[config.ORB_BASE_TIMEFRAME, config.BREAKOUT_TIMEFRAME]
    )(_signal_engine)

    # =========================================================================
    # Motores de Sizing y Riesgo
    # =========================================================================
    symbol_risk_pct = config.RISK_PCT / len(config.SYMBOLS) if config.SYMBOLS else config.RISK_PCT
    sizing_config = RiskPctSizingConfig(risk_pct=symbol_risk_pct)
    risk_config = MinSizingConfig()

    s.configure_predefined_sizing_engine(sizing_config)
    s.configure_predefined_risk_engine(risk_config)

    @s.custom_risk_engine(strategy_id=config.STRATEGY_ID)
    def _risk_engine(suggested_order: SuggestedOrder, modules: Modules) -> float:
        vol = suggested_order.volume
        sym = suggested_order.signal_event.symbol.rstrip("+")
        entry = suggested_order.signal_event.order_price
        sl = suggested_order.signal_event.sl
        tp = suggested_order.signal_event.tp
        sig_type = suggested_order.signal_event.signal_type
        ts = suggested_order.signal_event.time_generated
        signal_session = state.current_session_for_signal.get(sym, state.current_session)

        if vol == Decimal('0.0'):
            state.skipped["wide_sl"][sym] = state.skipped["wide_sl"].get(sym, 0) + 1
            dist = abs(entry - sl)
            eq = modules.PORTFOLIO.get_account_equity()
            vol_step = Decimal('0.01')
            csize = Decimal('100')
            max_dist = eq * Decimal(str(symbol_risk_pct)) / Decimal('100') / (vol_step * csize)
            label = "BUY" if sig_type == SignalType.BUY else "SELL"
            logger.info(
                f"{TerminalColors.WARNING}[{signal_session}] [{ts.strftime('%Y-%m-%d %H:%M:%S')}] [{sym}]: "
                f"{label} trade @{entry:.2f} with TP @{tp:.2f} and SL @{sl:.2f} skipped due to: "
                f"SL too wide ({dist:.2f} pips vs max {float(max_dist):.2f} pips){TerminalColors.ENDC}"
            )
        else:
            bal = modules.PORTFOLIO.get_account_balance()
            eq = modules.PORTFOLIO.get_account_equity()
            logger.info(
                f"[{signal_session}] [{ts.strftime('%Y-%m-%d %H:%M:%S')}] [{sym}]: "
                f"Account: Balance ${float(bal):.2f} | Equity ${float(eq):.2f} | Volume {float(vol):.2f} lot"
            )
        return float(vol)

    # =========================================================================
    # Hooks
    # =========================================================================
    _on_fill_hook = make_on_fill_hook(
        state, config.STRATEGY_SYMBOLS, symbol_risk_pct, config.BROKER, config.SESSIONS, orb_strat
    )
    s.hook(Hooks.ON_FILL_EVENT)(_on_fill_hook)

    _on_end_hook = make_on_end_hook(
        state, config.STRATEGY_SYMBOLS, config.RISK_PCT, symbol_risk_pct,
        config.ENTRY_METHOD.value, config.SL_METHOD.value, config.TP_METHOD.value, config.BROKER
    )
    s.hook(Hooks.ON_END)(_on_end_hook)

    # =========================================================================
    # Ejecución
    # =========================================================================
    if config.MODE == "BACKTEST":
        from impl.backtest.data_downloader import ensure_backtest_data_for_symbols
        ensure_backtest_data_for_symbols(
            symbols=config.STRATEGY_SYMBOLS,
            start_date=config.DATA_FROM,
            end_date=config.DATA_TO,
            csv_dir="impl/backtest/historical_data",
        )

        s.backtest(
            strategy_id=config.STRATEGY_ID,
            initial_capital=config.STARTING_CAPITAL,
            symbols_to_trade=config.STRATEGY_SYMBOLS,
            csv_dir="impl/backtest/historical_data",
            backtest_name=f"{config.STRATEGY_ID}_{config.ENTRY_METHOD.value}_{config.SL_METHOD.value}_{config.TP_METHOD.value}",
            start_date=config.BT_FROM,
            end_date=config.BT_TO,
            export_backtest_parquet=False,
            account_currency=AccountCurrencies.USD
        )

    elif config.MODE == "LIVE":
        mt5_config = Mt5PlatformConfig(
            path=config.MT5_PATH,
            login=config.MT5_LOGIN,
            password=config.MT5_PASSWORD,
            server=config.MT5_SERVER,
            timeout=config.MT5_TIMEOUT,
            portable=False
        )

        if not mt5.initialize(
            path=mt5_config.path, login=mt5_config.login,
            password=mt5_config.password, server=mt5_config.server,
            timeout=mt5_config.timeout
        ):
            logger.error("MT5 initialization failed")
            mt5.shutdown()
            sys.exit(1)
            
        live_balance = float(mt5.account_info()._asdict()['balance'])
        mt5.shutdown()
        logger.info(f"[SYS] [---] [---]: Account balance: ${live_balance:.2f}")

        try:
            s.run_live(
                mt5_configuration=mt5_config,
                strategy_id=config.STRATEGY_ID,
                initial_capital=live_balance,
                symbols_to_trade=mt5_symbols,
                heartbeat=0.1
            )
            logger.info("[SYS] [---] [---]: Live trading started. Monitoring market...")
        except Exception as e:
            logger.error(f"Error durante el live trading: {e}")
            mt5.shutdown()


if __name__ == "__main__":
    main()
