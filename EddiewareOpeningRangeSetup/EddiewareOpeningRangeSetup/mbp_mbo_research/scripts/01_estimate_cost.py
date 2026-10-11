"""Estimate Databento cost/size for the OR window, per schema, from sample days.

Metadata calls are free, so we price a handful of representative sessions and
extrapolate to the full backtest range.
"""
from __future__ import annotations

import sys
from datetime import date

import databento as db
import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from config import (DATASET, MBO_END, MBO_START, MBP10_END, MBP10_START,
                    STYPE_IN, SYMBOL, load_api_key, ny_window_utc)

SAMPLE_DAYS = [date(2024, 2, 14), date(2024, 6, 12), date(2024, 10, 9),
               date(2025, 3, 12), date(2025, 7, 16), date(2025, 11, 12)]

SCHEMAS = {
    "mbp-10": (MBP10_START, MBP10_END),
    "mbo": (MBO_START, MBO_END),
    "trades": (MBP10_START, MBP10_END),
    "tbbo": (MBP10_START, MBP10_END),
}

load_api_key()
client = db.Historical()

rng = client.metadata.get_dataset_range(dataset=DATASET)
print(f"{DATASET} available range: {rng}\n")

rows = []
for schema, (t0, t1) in SCHEMAS.items():
    for day in SAMPLE_DAYS:
        start, end = ny_window_utc(day, t0, t1)
        kw = dict(dataset=DATASET, symbols=SYMBOL, stype_in=STYPE_IN,
                  schema=schema, start=start, end=end)
        cost = client.metadata.get_cost(**kw)
        size = client.metadata.get_billable_size(**kw)
        rows.append({"schema": schema, "day": day,
                     "minutes": int((pd.Timestamp(end) - pd.Timestamp(start)).total_seconds() // 60),
                     "MB": size / 1e6, "usd_day": cost})
        print(f"  {schema:8s} {day} {size/1e6:9.1f} MB  ${cost:8.4f}")

df = pd.DataFrame(rows)
out = df.groupby("schema").agg(minutes=("minutes", "max"), MB_day=("MB", "mean"),
                               usd_day=("usd_day", "mean")).reset_index()
for days, label in [(252, "1 year"), (504, "2 years"), (1260, "5 years")]:
    out[f"usd_{label.replace(' ', '')}"] = (out.usd_day * days).round(2)
    out[f"GB_{label.replace(' ', '')}"] = (out.MB_day * days / 1000).round(1)

pd.set_option("display.width", 200)
print("\n=== Cost per schema (OR window only) ===")
print(out.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
out.to_csv("logs/cost_estimate.csv", index=False)
