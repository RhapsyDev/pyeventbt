"""
Script Unificado de Backtests para PyEventBT
-------------------------------------------
Modifica las fechas y combinaciones en la sección CONFIGURACIÓN DEL TEST.
"""

# =============================================================================
# CONFIGURACIÓN DEL TEST
# =============================================================================
FROM_DATE = "2026-06-01"
TO_DATE   = "2026-07-01"
STRATEGY_PATH = "impl/strategies/orb_advanced/main.py"
REPORT_NAME = "orb_advanced_report"

COMBINATIONS = [
    # Puedes usar "symbols" específicos (ej: ["XAUUSD", "BTCUSD"]) o dejarlo
    # vacío/no poner la key para que use todos los del config.
    {"symbols": ["XAUUSD", "BTCUSD"], "entry": "BREAKOUT", "sl": "OPPOSITE_RANGE", "tp": "FIXED_1R"},
    {"symbols": ["XAUUSD", "BTCUSD"], "entry": "RETEST",   "sl": "OPPOSITE_RANGE", "tp": "TRAILING"},
    
    # Aquí puedes añadir más escenarios
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
        ("#", 3), ("Scenario", 15), ("Entry", 10), ("SL", 16), ("TP", 12),
        ("Trades", 7), ("TPs", 5), ("SLs", 5), ("WR%", 6),
        ("Net", 10), ("Gross", 10), ("Fees", 7), ("WideSL", 7), ("Expired", 8),
    ]
    
    lines = []
    lines.append("=" * sum(w + 1 for _, w in cols))
    lines.append(f"  {title}")
    lines.append("=" * sum(w + 1 for _, w in cols))
    
    # Header
    hdr = "    " + " ".join(n.rjust(w) if n not in ("#", "Scenario", "Entry", "SL", "TP") else n.ljust(w) for n, w in cols)
    lines.append(hdr)
    lines.append("  " + "-" * (sum(w + 1 for _, w in cols) - 2))
    
    for i, r in enumerate(results):
        symbols_str = ",".join(r.get("symbols", ["ALL"]))
        if len(symbols_str) > 15: symbols_str = "MULTIPLE"
        
        vals = [
            str(i + 1).ljust(3),
            symbols_str.ljust(15),
            str(r.get("entry", "?")).ljust(10),
            str(r.get("sl", "?")).ljust(16),
            str(r.get("tp", "?")).ljust(12),
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
        return f"{','.join(r.get('symbols',['ALL']))}_{r.get('entry')}_{r.get('sl')}_{r.get('tp')}"

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
        label = f"{','.join(combo.get('symbols',['ALL']))}_{combo.get('entry', '')}_{combo.get('sl', '')}_{combo.get('tp', '')}"
        print(f"\n{'='*70}")
        print(f"  [{idx+1}/{len(COMBINATIONS)}] {label}")
        print(f"{'='*70}")

        cmd = [VENV_PYTHON, STRATEGY_PATH, "--mode", "BACKTEST", "--start-date", FROM_DATE, "--end-date", TO_DATE]
        
        if "symbols" in combo and combo["symbols"]:
            cmd.extend(["--symbols", ",".join(combo["symbols"])])
        if "entry" in combo: cmd.extend(["--entry", str(combo["entry"])])
        if "sl" in combo: cmd.extend(["--sl", str(combo["sl"])])
        if "tp" in combo: cmd.extend(["--tp", str(combo["tp"])])

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=BASE)
            output = proc.stdout + proc.stderr
        except subprocess.TimeoutExpired:
            output = "Timeout: 1\n"

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
