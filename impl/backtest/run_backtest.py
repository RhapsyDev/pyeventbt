"""
Script Unificado de Backtests para PyEventBT
-------------------------------------------
Modifica las fechas y combinaciones en la sección CONFIGURACIÓN DEL TEST.
"""

# =============================================================================
# CONFIGURACIÓN DEL TEST
# =============================================================================
FROM_DATE = "2026-07-10"
TO_DATE   = "2026-07-10"
STRATEGY_PATH = "impl/strategies/orb_advanced/main.py"
REPORT_NAME = "orb_advanced_report"

COMBINATIONS = [
    # Símbolos con datos disponibles en el rango FROM_DATE–TO_DATE
    {"symbols": ["XAUUSD", "NAS100"], "entry": "BREAKOUT",           "sl": "OPPOSITE_RANGE", "tp": "FIXED", "rr": 1.0},
    {"symbols": ["XAUUSD", "NAS100"], "entry": "RETEST_ORB",         "sl": "OPPOSITE_RANGE", "tp": "FIXED", "rr": 1.5},
    {"symbols": ["XAUUSD"],           "entry": "BREAKOUT",           "sl": "MID_RANGE",      "tp": "TRAILING"},
    {"symbols": ["XAUUSD", "NAS100"], "entry": "BREAKOUT_CONFIRMED", "sl": "OPPOSITE_RANGE", "tp": "FIXED", "rr": 1.0},
    {"symbols": ["XAUUSD"],           "entry": "FVG_RETEST",         "sl": "OPPOSITE_RANGE", "tp": "FIXED", "rr": 1.5},
]
# =============================================================================


import os
import sys
import subprocess
import re
import json
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VENV_PYTHON = os.path.join(BASE, "venv", "Scripts", "python.exe")


def parse_output(output: str) -> dict:
    """Extrae las métricas del log stdout del framework."""
    r = {}
    patterns = [
        ("days", r"Days tested:\s+(\d+)", int),
        ("trades", r"Trades:\s+(\d+)", int),
        ("tp_count", r"TP's:\s+(\d+)", int),
        ("sl_count", r"SL's:\s+(\d+)", int),
        ("gross", r"Gross PnL:\s+([+-]\d+\.\d+)", float),
        ("fees", r"Total Fees:\s+-?(\d+\.\d+)", float),
        ("winrate", r"Win Rate:\s+(\d+\.\d)%", float),
        ("net", r"Net Profit:\s+([+-]\d+\.\d+)", float),
        ("wide_sl", r"wide_sl:\s+(\d+)", int),
        ("expired", r"expired:\s+(\d+)", int),
    ]
    for key, pat, cast in patterns:
        m = re.search(pat, output)
        if m:
            r[key] = cast(m.group(1))
    return r


def format_table(results: list, title: str) -> str:
    """Formatea la lista de resultados en una tabla ASCII limpia."""
    cols = [
        ("#", 3), ("Scenario", 15), ("Entry", 10), ("SL", 16), ("TP", 10), ("RR", 5),
        ("Trades", 7), ("TPs", 5), ("SLs", 5), ("WR%", 6),
        ("Net", 10), ("Gross", 10), ("Fees", 7), ("WideSL", 7), ("Expired", 8),
    ]
    
    lines = []
    lines.append("=" * sum(w + 1 for _, w in cols))
    lines.append(f"  {title}")
    lines.append("=" * sum(w + 1 for _, w in cols))
    
    # Header
    hdr = "    " + " ".join(n.rjust(w) if n not in ("#", "Scenario", "Entry", "SL", "TP", "RR") else n.ljust(w) for n, w in cols)
    lines.append(hdr)
    lines.append("  " + "-" * (sum(w + 1 for _, w in cols) - 2))
    
    for i, r in enumerate(results):
        symbols_str = ",".join(r.get("symbols", ["ALL"]))
        if len(symbols_str) > 15: symbols_str = "MULTIPLE"
        
        tp_val = r.get("tp", "?")
        rr_val = r.get("rr", "")
        display_tp = tp_val
        display_rr = str(rr_val) if rr_val != "" else ""
        if tp_val == "FIXED" and rr_val != "":
            display_tp = "FIXED"
            display_rr = str(rr_val)

        vals = [
            str(i + 1).ljust(3),
            symbols_str.ljust(15),
            str(r.get("entry", "?")).ljust(10),
            str(r.get("sl", "?")).ljust(16),
            display_tp.ljust(10),
            display_rr.rjust(5),
            str(r.get("trades", 0)).rjust(7),
            str(r.get("tp_count", 0)).rjust(5),
            str(r.get("sl_count", 0)).rjust(5),
            f"{r.get('winrate', 0.0):.1f}%".rjust(6),
            f"${(r.get('net', 0)):+,.2f}".rjust(10),
            f"${(r.get('gross', 0)):+,.2f}".rjust(10),
            f"${(r.get('fees', 0)):,.2f}".rjust(7),
            str(r.get("wide_sl", 0)).rjust(7),
            str(r.get("expired", 0)).rjust(8),
        ]
        lines.append("    " + " ".join(vals))
        
    lines.append("=" * sum(w + 1 for _, w in cols))
    return "\n".join(lines)


def format_summary(results: list) -> str:
    """Extrae the best and worst metrics."""
    valid = [r for r in results if "net" in r]
    if not valid: return ""
    
    best_net = max(valid, key=lambda x: x["net"])
    worst_net = min(valid, key=lambda x: x["net"])
    best_wr = max(valid, key=lambda x: x.get("winrate", 0))
    worst_wr = min(valid, key=lambda x: x.get("winrate", 0))
    
    def get_name(r):
        tp_str = r.get('tp', '')
        if tp_str == "FIXED" and "rr" in r:
            tp_str = f"FIXED_{r['rr']}R"
        return f"{','.join(r.get('symbols',['ALL']))}_{r.get('entry')}_{r.get('sl')}_{tp_str}"

    return "\n".join([
        f"  BEST NET PROFIT : {get_name(best_net)} -> ${best_net['net']:+.2f}  (WR={best_net.get('winrate',0):.1f}%, Trades={best_net.get('trades',0)})",
        f"  WORST NET PROFIT: {get_name(worst_net)} -> ${worst_net['net']:+.2f}  (WR={worst_net.get('winrate',0):.1f}%, Trades={worst_net.get('trades',0)})",
        f"  BEST WIN RATE   : {get_name(best_wr)} -> {best_wr.get('winrate',0):.1f}%  (Net=${best_wr['net']:+.2f}, Trades={best_wr.get('trades',0)})",
        f"  WORST WIN RATE  : {get_name(worst_wr)} -> {worst_wr.get('winrate',0):.1f}%  (Net=${worst_wr['net']:+.2f}, Trades={worst_wr.get('trades',0)})",
    ])


def main():
    print(f"\n  Campaign: {REPORT_NAME}")
    print(f"  Strategy: {STRATEGY_PATH}")
    print(f"  Dates:    {FROM_DATE} to {TO_DATE}")
    print(f"  Combos:   {len(COMBINATIONS)}")
    print(f"{'='*70}\n")

    results = []
    out_dir = os.path.join(BASE, "impl", "backtest", "results", REPORT_NAME)
    os.makedirs(out_dir, exist_ok=True)

    for idx, combo in enumerate(COMBINATIONS):
        tp_str = combo.get('tp', '')
        if tp_str == "FIXED" and "rr" in combo:
            tp_str = f"FIXED_{combo['rr']}R"
        label = f"{','.join(combo.get('symbols',['ALL']))}_{combo.get('entry', '')}_{combo.get('sl', '')}_{tp_str}"
        print(f"\n{'='*70}")
        print(f"  [{idx+1}/{len(COMBINATIONS)}] {label}")
        print(f"{'='*70}")

        cmd = [VENV_PYTHON, STRATEGY_PATH, "--mode", "BACKTEST", "--start-date", FROM_DATE, "--end-date", TO_DATE]
        
        if "symbols" in combo and combo["symbols"]:
            cmd.extend(["--symbols", ",".join(combo["symbols"])])
        if "entry" in combo: cmd.extend(["--entry", str(combo["entry"])])
        if "sl" in combo: cmd.extend(["--sl", str(combo["sl"])])
        if "tp" in combo: cmd.extend(["--tp", str(combo["tp"])])
        if "rr" in combo: cmd.extend(["--rr", str(combo["rr"])])

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=BASE)
            output = proc.stdout + proc.stderr
        except subprocess.TimeoutExpired:
            output = "TIMEOUT_ERROR_OCURRED\n"

        parsed = parse_output(output)
        parsed.update(combo)
        results.append(parsed)

        net = parsed.get("net", 0)
        wr = parsed.get("winrate", 0.0)
        fees = parsed.get("fees", 0.0)
        print(f"  Days={parsed.get('days','?')}  Trades={parsed.get('trades','?')}  "
              f"TPs={parsed.get('tp_count','?')}  SLs={parsed.get('sl_count','?')}  "
              f"WR={wr:.1f}%  Net=${net:+.2f}  "
              f"Fees=${fees:.2f}")

    print(f"\n{'='*70}")
    table_str = format_table(results, title=REPORT_NAME.upper())
    print(table_str)
    print()
    summary_str = format_summary(results)
    print(summary_str)

    # Guardar reporte
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = os.path.join(out_dir, f"{REPORT_NAME}_{ts}.txt")
    with open(txt_path, "w") as f:
        f.write(table_str + "\n\n" + summary_str + "\n")
    print(f"\n  Saved: {txt_path}")


if __name__ == "__main__":
    main()
