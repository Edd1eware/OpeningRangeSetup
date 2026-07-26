"""Live Databento sample quote for bounded YM+RTY early-session data."""

from __future__ import annotations

import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import databento as db
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
NQ_ROOT = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
    r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_2"
)
KEY_PATH = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
    r"\databento_api_key.txt"
)
OUT = BASE / "QUOTE_SAMPLE_YM_RTY.json"
NY = ZoneInfo("America/New_York")
DATASET = "GLBX.MDP3"
SYMBOLS = ["YM.c.0", "RTY.c.0"]
SCHEMA = "ohlcv-1s"
STYPE = "continuous"
DATE_START = "2022-04-25"
DATE_END = "2026-06-30"
SAMPLE_SIZE = 12


def bounds(date: str) -> tuple[str, str]:
    start = pd.Timestamp(f"{date} 09:25:00", tz=NY).tz_convert("UTC")
    end = pd.Timestamp(f"{date} 10:05:00", tz=NY).tz_convert("UTC")
    return start.isoformat(), end.isoformat()


def main() -> int:
    dates = sorted(
        path.name for path in NQ_ROOT.iterdir()
        if path.is_dir() and DATE_START <= path.name <= DATE_END
    )
    positions = np.linspace(0, len(dates) - 1, SAMPLE_SIZE, dtype=int)
    sample = [dates[index] for index in positions]
    client = db.Historical(KEY_PATH.read_text(encoding="utf-8").strip())
    rows = []
    for index, date in enumerate(sample, start=1):
        start, end = bounds(date)
        for attempt in range(8):
            try:
                cost = float(
                    client.metadata.get_cost(
                        dataset=DATASET,
                        symbols=SYMBOLS,
                        schema=SCHEMA,
                        start=start,
                        end=end,
                        stype_in=STYPE,
                    )
                )
                break
            except Exception:
                if attempt == 7:
                    raise
                time.sleep(min(3 * (attempt + 1), 15))
        rows.append({"date": date, "cost_usd": round(cost, 6)})
        print(
            f"[{index:02d}/{len(sample)}] {date} cost=${cost:.6f}",
            flush=True,
        )
        if index < len(sample):
            time.sleep(3)
    costs = np.array([row["cost_usd"] for row in rows], dtype=float)
    projected = float(costs.mean() * len(dates))
    result = {
        "dataset": DATASET,
        "symbols": SYMBOLS,
        "schema": SCHEMA,
        "window_ny": "09:25:00..10:05:00",
        "date_range": [DATE_START, DATE_END],
        "session_count": len(dates),
        "sample_count": len(rows),
        "sample_rows": rows,
        "sample_cost_mean_usd": round(float(costs.mean()), 6),
        "sample_cost_median_usd": round(float(np.median(costs)), 6),
        "sample_cost_max_usd": round(float(costs.max()), 6),
        "projected_total_usd_mean": round(projected, 4),
        "projected_total_usd_with_25pct_margin": round(projected * 1.25, 4),
        "downloads_performed": 0,
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
