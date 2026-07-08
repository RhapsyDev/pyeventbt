"""
hooks.py — Hooks de pyeventbt para la estrategia ORB Advanced.

Los hooks se registran en pyeventbt para reaccionar a eventos del framework:
  - ON_FILL_EVENT : Se llama cada vez que una posición es abierta o cerrada.
  - ON_END        : Se llama al terminar el backtest o detener el live.

Este módulo expone funciones de fábrica que construyen los hooks como closures,
recibiendo las dependencias (state, config) en lugar de acceder a globales.
"""

from decimal import Decimal
from datetime import datetime
from typing import List

from pyeventbt import Modules, FillEvent
from pyeventbt.events.events import SignalType
from pyeventbt.utils.utils import TerminalColors


def _clean_symbol(s: str) -> str:
    return s.rstrip("+")


def _fmt_time(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def log_prefix(session: str, ts: datetime, symbol: str) -> str:
    return f"[{session}] [{_fmt_time(ts)}] [{symbol}]:"


# =============================================================================
# Utilidad de impresión de tablas (compartida entre _on_fill y _on_end)
# =============================================================================

def _print_results_table(
    results: List[dict],
    symbols: List[str],
    title: str = "Session Summary",
    dates_str: str = "",
):
    """Imprime una tabla con los resultados de las operaciones cerradas."""
    print()
    print(f"{'=' * 70}")
    print(f"  {title}{dates_str}")
    print(f"{'=' * 70}")

    sym_stats: dict = {}
    for t in results:
        sym = t["symbol"]
        if sym not in sym_stats:
            sym_stats[sym] = {"trades": 0, "tp": 0, "sl": 0, "eod": 0, "gross": 0, "fees": 0, "net": 0}
        s = sym_stats[sym]
        s["trades"] += 1
        s["gross"]  += float(t["gross_profit"])
        s["fees"]   += float(t["fee"])
        s["net"]    += float(t["profit"])
        reason_key = t["reason"].lower()
        if reason_key in s:
            s[reason_key] += 1

    cols = [
        ("Symbol", 24, "l"),
        ("Trades",  6, "r"),
        ("TP",      4, "r"),
        ("SL",      3, "r"),
        ("EOD",     4, "r"),
        ("WR%",     6, "r"),
        ("Gross",   8, "r"),
        ("Fees",    8, "r"),
        ("Net",     8, "r"),
    ]
    hdr = "  " + " ".join((n.rjust(w) if a == "r" else n.ljust(w)) for n, w, a in cols)
    print(hdr)
    print("  " + "-" * (sum(w for _, w, _ in cols) + len(cols) - 1))

    for sym in symbols:
        if sym not in sym_stats:
            cells = [
                sym.ljust(24), "0".rjust(6), "0".rjust(4), "0".rjust(3), "0".rjust(4),
                "---".rjust(6), "0.00".rjust(8), "0.00".rjust(8), "0.00".rjust(8),
            ]
            print("  " + " ".join(cells))
            continue
        s = sym_stats[sym]
        wr = f"{s['tp'] / s['trades'] * 100:>5.1f}%" if s["trades"] > 0 else "  ---"
        net_str = f"{s['net']:>+8.2f}"
        net_color = TerminalColors.OKGREEN if s["net"] > 0 else (TerminalColors.FAIL if s["net"] < 0 else "")
        cells = [
            sym.ljust(24),
            str(s["trades"]).rjust(6),
            str(s["tp"]).rjust(4),
            str(s["sl"]).rjust(3),
            str(s["eod"]).rjust(4),
            wr.rjust(6),
            f"{s['gross']:>+8.2f}",
            f"{s['fees']:>8.2f}",
            f"{net_color}{net_str}{TerminalColors.ENDC}" if net_color else net_str,
        ]
        print("  " + " ".join(cells))

    print("  " + "-" * (sum(w for _, w, _ in cols) + len(cols) - 1))

    total   = len(results)
    tp_cnt  = sum(1 for t in results if t["reason"] == "TP")
    sl_cnt  = sum(1 for t in results if t["reason"] == "SL")
    eod_cnt = sum(1 for t in results if t["reason"] == "EOD")
    gross   = sum(float(t["gross_profit"]) for t in results)
    fees    = sum(float(t["fee"]) for t in results)
    net     = sum(float(t["profit"]) for t in results)
    wr      = f"{tp_cnt / total * 100:>5.1f}%" if total > 0 else "  ---"
    net_str = f"{net:>+8.2f}"
    pft_col = TerminalColors.OKGREEN if net > 0 else (TerminalColors.FAIL if net < 0 else "")
    cells = [
        "TOTAL".ljust(24),
        str(total).rjust(6),
        str(tp_cnt).rjust(4),
        str(sl_cnt).rjust(3),
        str(eod_cnt).rjust(4),
        wr.rjust(6),
        f"{gross:>+8.2f}",
        f"{fees:>8.2f}",
        f"{pft_col}{net_str}{TerminalColors.ENDC}" if pft_col else net_str,
    ]
    print("  " + " ".join(cells))
    print(f"{'=' * 70}")


# =============================================================================
# Fábricas de hooks
# =============================================================================

def _get_next_session_info(current_time: datetime, sessions: dict) -> str:
    """Devuelve un string describiendo la próxima sesión habilitada."""
    enabled = sorted(
        [(sn, sc) for sn, sc in sessions.items() if sc["enabled"]],
        key=lambda x: x[1]["start_time"],
    )
    if not enabled:
        return "next day..."
    current_t = current_time.time()
    for sn, sc in enabled:
        if sc["start_time"] > current_t:
            return f"{sn} at {sc['start_time'].strftime('%H:%M')}"
    first_sn, first_sc = enabled[0]
    return f"next {first_sn} at {first_sc['start_time'].strftime('%H:%M')}"


def make_on_fill_hook(state, strategy_symbols, symbol_risk_pct, broker, sessions, orb_strat):
    """
    Construye el hook ON_FILL_EVENT como closure con las dependencias necesarias.

    Parámetros
    ----------
    state            : ORBStateManager
    strategy_symbols : list[str]
    symbol_risk_pct  : float — porcentaje de riesgo por símbolo
    broker           : BrokerBase — para calcular la comisión en OUT
    sessions         : dict — configuración de sesiones (para calcular next session)
    orb_strat        : ORBAdvancedStrategy — para acceder al strategy_state
    """
    def _on_fill(modules: Modules, event: FillEvent) -> None:
        event_symbol = _clean_symbol(event.symbol)

        if event.deal == "IN":
            for i, sig in enumerate(state.pending_signals):
                if (
                    _clean_symbol(sig["symbol"]) == event_symbol
                    and sig["signal_type"] == event.signal_type
                    and sig["entry"] > 0
                ):
                    state.position_map[event.position_id] = {
                        "entry":       sig["entry"],
                        "sl":          sig["sl"],
                        "tp":          sig["tp"],
                        "signal_type": sig["signal_type"],
                        "symbol":      event_symbol,
                        "volume":      event.volume,
                        "session":     sig["session"],
                    }
                    state.session_positions.setdefault(sig["session"], set()).add(event.position_id)
                    state.pending_signals.pop(i)

                    eq       = modules.PORTFOLIO.get_account_equity()
                    max_risk = float(eq) * symbol_risk_pct / 100
                    side_label = (
                        f"{TerminalColors.OKGREEN}BUY{TerminalColors.ENDC}"
                        if sig["signal_type"] == SignalType.BUY
                        else f"{TerminalColors.FAIL}SELL{TerminalColors.ENDC}"
                    )
                    import logging
                    logger = logging.getLogger("pyeventbt")
                    logger.info(
                        f"{log_prefix(sig['session'], event.time_generated, event_symbol)} "
                        f"{side_label} Filled {float(event.volume):.2f} lot @ {float(event.price):.2f} "
                        f"TP={float(sig['tp']):.2f}  SL={float(sig['sl']):.2f} | "
                        f"Risk {symbol_risk_pct:.2f}% ${max_risk:.2f}"
                    )
                    break

        elif event.deal == "OUT":
            pos = state.position_map.get(event.position_id)
            if pos is None:
                return

            # Determinar motivo de cierre por proximidad al nivel objetivo
            tp    = pos["tp"]
            sl    = pos["sl"]
            price = event.price
            dist_tp = abs(price - tp) if tp > 0 else Decimal("Infinity")
            dist_sl = abs(price - sl) if sl > 0 else Decimal("Infinity")
            tol = max(price * Decimal("0.0002"), Decimal("0.02"))

            if dist_tp < dist_sl and dist_tp <= tol:
                reason = "TP"
            elif dist_sl <= dist_tp and dist_sl <= tol:
                reason = "SL"
            else:
                reason = "EOD"

            fee   = broker.calc_commission(event_symbol, event.volume, event.price)
            gross = event.gross_profit
            net   = gross - fee

            color = (
                TerminalColors.OKGREEN if reason == "TP"
                else (TerminalColors.FAIL if reason == "SL" else "")
            )
            import logging
            logger = logging.getLogger("pyeventbt")
            logger.info(
                f"{color}{log_prefix(pos['session'], event.time_generated, event_symbol)} "
                f"{reason} reached: Gross ${float(gross):+.2f} | Fee -${float(fee):.2f} | "
                f"Net ${float(net):+.2f}{TerminalColors.ENDC}"
            )

            state.trade_results.append({
                "position_id": event.position_id,
                "symbol":      event_symbol,
                "reason":      reason,
                "gross_profit": gross,
                "fee":         fee,
                "profit":      net,
                "date":        event.time_generated,
            })
            state.closed_tickets.add(event.position_id)

            # Imprimir resumen de sesión cuando todos sus trades cerraron
            pos_session   = pos["session"]
            sess_positions = state.session_positions.get(pos_session, set())
            session_done = all(
                orb_strat.strategy_state[sym][pos_session].breakout_attempted
                for sym in strategy_symbols
            )
            if (
                pos_session not in state.summarized_sessions
                and len(sess_positions) > 0
                and sess_positions.issubset(state.closed_tickets)
                and session_done
            ):
                state.summarized_sessions.add(pos_session)
                sess_results = [t for t in state.trade_results if t["position_id"] in sess_positions]
                next_info = _get_next_session_info(event.time_generated, sessions)
                import logging
                logging.getLogger("pyeventbt").info(
                    f"[SYS] [{_fmt_time(event.time_generated)}] [---]: "
                    f"All positions closed for {pos_session} session. Waiting for {next_info}..."
                )
                dates = set()
                for t in sess_results:
                    if "date" in t:
                        dates.add(str(t["date"].date()) if hasattr(t["date"], "date") else str(t["date"]))
                dates_str = f" ({', '.join(sorted(dates))})" if dates else ""
                _print_results_table(sess_results, strategy_symbols, f"{pos_session} Session Summary", dates_str)

    return _on_fill


def make_on_end_hook(state, strategy_symbols, risk_pct, symbol_risk_pct, entry_method, sl_method, tp_method, broker):
    """
    Construye el hook ON_END como closure.
    Imprime el resumen final del backtest/live con todos los parámetros usados.
    """
    def _on_end(modules: Modules) -> None:
        results = state.trade_results
        tps    = [t for t in results if t["reason"] == "TP"]
        sls    = [t for t in results if t["reason"] == "SL"]
        eods   = [t for t in results if t["reason"] == "EOD"]

        total      = len(results)
        win_rate   = (len(tps) / total * 100) if total > 0 else 0
        total_gross = sum(t["gross_profit"] for t in results)
        total_fees  = sum(t["fee"] for t in results)
        total_net   = sum(t["profit"] for t in results)
        tp_net  = sum(t["profit"] for t in tps)
        sl_net  = sum(t["profit"] for t in sls)
        eod_net = sum(t["profit"] for t in eods)

        total_skipped   = sum(sum(v.values()) for v in state.skipped.values())
        total_cancelled = sum(sum(v.values()) for v in state.cancelled.values())

        print(f"{TerminalColors.ENDC}")
        print()
        print("=" * 100)
        _print_results_table(results, strategy_symbols, title="BACKTEST RESULTS — By Symbol")
        print()
        print("=" * 100)
        print("  Parámetros de la Estrategia")
        print(f"  Entry={entry_method}  SL={sl_method}  TP={tp_method}  RISK={risk_pct}%")
        print(f"  Broker: {broker.name}")
        print("=" * 100)
        print(f"  Days tested: {state.days_tested}")
        print(f"  Trades:      {total}")

        tp_col = TerminalColors.OKGREEN
        sl_col = TerminalColors.FAIL
        print(f"  {tp_col}TP's:        {len(tps)}  ({tp_net:+.2f} net){TerminalColors.ENDC}")
        print(f"  {sl_col}SL's:        {len(sls)}  ({sl_net:+.2f} net){TerminalColors.ENDC}")

        eod_col = TerminalColors.OKGREEN if eod_net > 0 else (TerminalColors.FAIL if eod_net < 0 else "")
        print(f"  {eod_col}EOD's:       {len(eods)}  ({eod_net:+.2f} net){TerminalColors.ENDC if eod_col else ''}")

        print(f"  Skipped:     {total_skipped}")
        for reason, per_sym in state.skipped.items():
            total_r = sum(per_sym.values())
            if total_r > 0:
                parts = [f"{sym}:{c}" for sym, c in sorted(per_sym.items()) if c > 0]
                print(f"    - {reason}: {total_r} ({', '.join(parts)})")

        print(f"  Cancelled:   {total_cancelled}")
        for reason, per_sym in state.cancelled.items():
            total_r = sum(per_sym.values())
            if total_r > 0:
                parts = [f"{sym}:{c}" for sym, c in sorted(per_sym.items()) if c > 0]
                print(f"    - {reason}: {total_r} ({', '.join(parts)})")

        pft_col = TerminalColors.OKGREEN if total_net > 0 else (TerminalColors.FAIL if total_net < 0 else "")
        wr_col  = TerminalColors.OKGREEN if win_rate >= 50 else TerminalColors.FAIL

        print(f"  Gross PnL:         {total_gross:+.2f}")
        print(f"  Total Fees:        -{total_fees:.2f}")
        print(f"  {wr_col}Win Rate:          {win_rate:.1f}%{TerminalColors.ENDC}")
        print(f"  {pft_col}Net Profit:        {total_net:+.2f}{TerminalColors.ENDC}")
        print(f"  {pft_col}Realised PnL (FW): {float(modules.PORTFOLIO._realised_pnl):+.2f}{TerminalColors.ENDC}")
        print("=" * 100)

    return _on_end
