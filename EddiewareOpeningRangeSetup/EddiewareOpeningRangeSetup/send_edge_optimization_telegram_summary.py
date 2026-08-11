import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

from telegram_run_summary_after_sync import (
    clear_telegram_before_run,
    compute_run_stats,
    send_text,
)


PROJECT_DIR = Path(__file__).resolve().parent
RESULTS_FOLDER = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
)
RUN_PARENT = (
    RESULTS_FOLDER
    / "visual_tests"
    / "04_run_replay_score_trade_results_dst_2025_2026_runs"
)
OUTPUTS_DIR = PROJECT_DIR / "outputs"


def _latest_summary_path():
    candidates = sorted(
        OUTPUTS_DIR.glob("edge_optimization_fast_*/summary.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _fmt_num(value, suffix="", digits=2, signed=False):
    if value in (None, ""):
        return "N/A"
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return "N/A"
    sign = "+" if signed else ""
    return f"{number:{sign}.{digits}f}{suffix}"


def _fmt_money(value):
    if value in (None, ""):
        return "N/A"
    try:
        return f"${float(value):+,.0f}"
    except (TypeError, ValueError):
        return str(value)


def _run_optimization():
    subprocess.run(
        [sys.executable, str(PROJECT_DIR / "edge_optimization_fast.py")],
        cwd=str(PROJECT_DIR),
        check=True,
    )


def _build_message(summary):
    raw = compute_run_stats(RUN_PARENT, run_names={"X10_R1"}) or {}
    best = summary.get("best", {})
    best_summary = summary.get("best_summary", {})
    sizing = summary.get("dynamic_sizing", {})
    dyn = summary.get("dynamic_summary", {})
    lucid = summary.get("lucid_150k", {})

    raw_pf = raw.get("pf")
    raw_pf_text = _fmt_num(raw_pf) if raw_pf is not None else "inf"

    lines = [
        "EW Opening Range | Resumen corregido",
        "Telegram limpiado antes de enviar este resumen.",
        "",
        "CRUDO X10:",
        (
            f"Trades {raw.get('trades', 0)} | TIME_OVER {raw.get('time_over', 0)} | "
            f"WR {_fmt_num(raw.get('winrate'), '%')} | PF {raw_pf_text} | "
            f"Exp {_fmt_num(raw.get('expectancy_ticks'), ' ticks', signed=True)} | "
            f"Net {_fmt_num(raw.get('profit_ticks'), ' ticks', digits=0, signed=True)}"
        ),
        "",
        "OPTIMIZADO ROBUSTO:",
        str(best.get("setup") or "N/A"),
        (
            f"Trades {best_summary.get('trades', 0)} | "
            f"{_fmt_num(summary.get('trades_per_month'), '/mes')} | "
            f"WR {_fmt_num(best_summary.get('wr'), '%')} | "
            f"PF {_fmt_num(best_summary.get('pf'))} | "
            f"Exp {_fmt_num(best_summary.get('expectancy'), ' ticks', signed=True)} | "
            f"DD {_fmt_num(best_summary.get('dd'), ' ticks', digits=0)}"
        ),
        "",
        "CONTRATOS 1/3/4:",
        str(sizing.get("rule") or "N/A"),
        (
            f"PF {_fmt_num(dyn.get('pf'))} | "
            f"Exp {_fmt_money(dyn.get('expectancy'))}/trade | "
            f"Profit {_fmt_money(dyn.get('profit'))} | "
            f"DD {_fmt_money(-abs(float(dyn.get('dd') or 0)))}"
        ),
        "",
        "LUCID 150K:",
        (
            f"Pass 3m {_fmt_num(lucid.get('pass_pct_3mo'), '%')} | "
            f"Bust 3m {_fmt_num(lucid.get('bust_pct_3mo'), '%')} | "
            f"DD95 {_fmt_money(-abs(float(lucid.get('dd_95_usd') or 0)))}"
        ),
        "",
        f"Eventos: {summary.get('event_count')} | Trades optimizados: {summary.get('executed_trades')}",
        f"Reporte: {summary.get('report_path')}",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-optimization", action="store_true")
    parser.add_argument("--clear-first", action="store_true")
    args = parser.parse_args()

    if args.run_optimization:
        _run_optimization()

    summary_path = _latest_summary_path()
    if summary_path is None:
        raise SystemExit("No encontre summary.json de optimizacion.")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if args.clear_first:
        clear_telegram_before_run(str(RESULTS_FOLDER))
    ok = send_text(str(RESULTS_FOLDER), _build_message(summary))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
