"""Lightweight Telegram status for MATRIX CLASSIFICATION TEST."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


STATUS_FILE = "telegram_lb_hypothesis.txt"


def calculate(results_folder: Path | str) -> dict[str, object]:
    root = Path(results_folder)
    path = root / "burst_causal_timeline.csv"
    if not path.exists() or path.stat().st_size == 0:
        return {"bursts": 0, "events": 0, "causal_pct": None, "sessions": 0}
    columns = [
        "BurstId", "Burst_Timestamp_UTC", "Decision_Timestamp_UTC",
        "Event_Causal_Timestamp_UTC", "Causal_Flag",
    ]
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    for column in ("Burst_Timestamp_UTC", "Decision_Timestamp_UTC", "Event_Causal_Timestamp_UTC"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    post = frame.loc[
        frame["Event_Causal_Timestamp_UTC"].ge(frame["Burst_Timestamp_UTC"])
        & frame["Event_Causal_Timestamp_UTC"].le(frame["Decision_Timestamp_UTC"])
    ]
    causal = pd.to_numeric(post["Causal_Flag"], errors="coerce").eq(1)
    if not causal.any():
        causal = post["Causal_Flag"].astype(str).str.lower().isin({"true", "1", "1.0"})
    return {
        "bursts": int(post["BurstId"].nunique()),
        "events": len(post),
        "causal_pct": float(100.0 * causal.mean()) if len(post) else None,
        "sessions": int(post["Burst_Timestamp_UTC"].dt.date.nunique()),
    }


def format_status(values: dict[str, object]) -> str:
    causal = values.get("causal_pct")
    causal_text = "CALCULANDO" if causal is None else f"{float(causal):.1f}% causal"
    return (
        "MATRIX CLASSIFICATION TEST : "
        f"{int(values.get('bursts', 0))} bursts post-LB | "
        f"{int(values.get('events', 0))} eventos | {causal_text} | "
        f"{int(values.get('sessions', 0))} sesiones"
    )


def update_status_file(results_folder: Path | str) -> str:
    root = Path(results_folder)
    root.mkdir(parents=True, exist_ok=True)
    status = format_status(calculate(root))
    (root / STATUS_FILE).write_text(status + "\n", encoding="utf-8")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_folder", type=Path)
    args = parser.parse_args()
    print(update_status_file(args.results_folder))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
