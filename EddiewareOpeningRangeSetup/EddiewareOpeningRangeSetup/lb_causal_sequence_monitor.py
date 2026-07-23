"""Lightweight Telegram progress monitor for causal DOM+tape capture."""

from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

import lb_causal_sequence_research as research


STATUS_FILE = "telegram_lb_hypothesis.txt"
RUN_ROOT_NAME = "04_run_replay_lb_causal_sequence_r4_dst_2025_2026_runs"


def _completed_sessions(root: Path) -> int:
    run_root = root / "visual_tests" / RUN_ROOT_NAME
    dates = set()
    if run_root.exists():
        for path in run_root.glob("X10_*/score_trade_result_*_NY.csv"):
            match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
            if match:
                dates.add(match.group(1))
    return len(dates)


def calculate(results_folder: Path | str) -> dict[str, object]:
    root = Path(results_folder)
    timeline = research.load_timeline(root)
    sessions = _completed_sessions(root)
    if timeline.empty:
        return {"sessions": sessions, "bursts": 0, "events": 0, "causal_pct": None}
    causal = (
        timeline["Event_Causal_Timestamp_UTC"].notna()
        & timeline["Decision_Timestamp_UTC"].notna()
        & timeline["Event_Causal_Timestamp_UTC"].le(timeline["Decision_Timestamp_UTC"])
    )
    return {
        "sessions": sessions,
        "bursts": int(timeline["BurstId"].nunique()),
        "events": len(timeline),
        "causal_pct": 100.0 * float(causal.mean()),
    }


def format_status(result: dict[str, object]) -> str:
    causal = result.get("causal_pct")
    causal_text = "CALCULANDO" if causal is None else f"{float(causal):.1f}% causal"
    return (
        "Secuencias causales DOM+tape : "
        f"{int(result.get('bursts', 0))} bursts | {int(result.get('events', 0))} eventos | "
        f"{causal_text} | {int(result.get('sessions', 0))} sesiones"
    )


def update_status_file(results_folder: Path | str) -> str:
    root = Path(results_folder)
    root.mkdir(parents=True, exist_ok=True)
    try:
        line = format_status(calculate(root))
    except Exception:
        line = "Secuencias causales DOM+tape : 0 bursts | 0 eventos | CALCULANDO | 0 sesiones"
    (root / STATUS_FILE).write_text(line + "\n", encoding="utf-8")
    return line


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_folder", type=Path)
    args = parser.parse_args()
    print(update_status_file(args.results_folder))
