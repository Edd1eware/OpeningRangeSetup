# -*- coding: utf-8 -*-
"""Find ROBUST feature ranges: positive EV in EVERY year (incl. 2024), keeping
frequency. No threshold optimisation - we use fixed tercile edges computed on
the pooled sample and demand the same bucket be positive across all years.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")
COMMISSION_TICKS = 2.0
MGMT = "trail_40_20_40"  # management column to evaluate (best worst-year gross)

feat = pd.read_csv(OUT_DIR / "orb_features_labels_1s.csv")
pnl = pd.read_csv(OUT_DIR / "orb_trailing_pnl.csv")
df = feat.merge(pnl[["date", MGMT] + [c for c in pnl.columns if c.startswith("fixed_")]],
                on="date", how="inner")
df["year"] = pd.to_datetime(df["date"]).dt.year
years = sorted(df["year"].unique())
print(f"Merged {len(df)} events | mgmt={MGMT} | years {years}\n")


def yearly_ev(sub):
    return {y: (sub[sub.year == y][MGMT].mean() - COMMISSION_TICKS) for y in years}


def line(name, sub):
    if len(sub) == 0:
        return
    evs = yearly_ev(sub)
    tot = sub[MGMT].mean() - COMMISSION_TICKS
    mo = pd.to_datetime(sub["date"]).dt.to_period("M").nunique()
    allpos = all(v > 0 for v in evs.values())
    flag = "  <-- POS ALL YEARS" if allpos else ""
    cells = " ".join(f"{y}:{evs[y]:>5.1f}" for y in years)
    print(f"{name:38s} n={len(sub):4d} t/mo={len(sub)/max(mo,1):4.1f} "
          f"tot={tot:5.1f} | {cells}{flag}")


# direction split
print("### by direction")
for d in ("UP", "DOWN"):
    line(f"direction={d}", df[(df.direction_up == (1.0 if d=="UP" else 0.0))])
print()

# candidate features to bucket (causal, interpretable)
cands = ["or_range_ticks", "breakout_delay_s", "dist_vwap", "vpt_30", "vts_10",
         "vvs_10", "dir_30", "rvol_30", "vol_30", "m1v_10", "dist_pdc", "round_50"]
print("### single-feature terciles (LOW / MID / HIGH), EV net by year")
for f in cands:
    if f not in df.columns:
        continue
    q1, q2 = df[f].quantile([1/3, 2/3])
    buckets = [("LOW", df[df[f] <= q1]),
               ("MID", df[(df[f] > q1) & (df[f] <= q2)]),
               ("HIGH", df[df[f] > q2])]
    print(f"-- {f}  (edges {q1:.1f} / {q2:.1f})")
    for bname, sub in buckets:
        line(f"   {f} {bname}", sub)
print()

# direction x or_range (robust 2-way)
print("### direction x or_range tercile")
for d in ("UP", "DOWN"):
    sd = df[(df.direction_up == (1.0 if d=="UP" else 0.0))]
    q1, q2 = sd["or_range_ticks"].quantile([1/3, 2/3])
    for bname, sub in [("smallOR", sd[sd.or_range_ticks <= q1]),
                       ("midOR", sd[(sd.or_range_ticks > q1) & (sd.or_range_ticks <= q2)]),
                       ("bigOR", sd[sd.or_range_ticks > q2])]:
        line(f"{d} {bname}", sub)
print()
