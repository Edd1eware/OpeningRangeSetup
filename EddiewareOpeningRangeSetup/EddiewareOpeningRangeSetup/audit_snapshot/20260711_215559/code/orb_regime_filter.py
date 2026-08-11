# -*- coding: utf-8 -*-
"""Causal regime gate: only trade when the market has recently been trending.

2024 is a chop regime (low breakout follow-through). We can only use PAST
information at entry, so we gate on the TRAILING trendiness of prior sessions
(|trend|/day_range averaged over the last K sessions, shifted so today is
excluded). Same rule every year (era-blind); it should throttle down in 2024
without hand-coding the year. We sweep K and the gate threshold and check that
2024 improves while 2022/23/25/26 are not destroyed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup"
               r"\..\..") and Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")
COMMISSION = 2.0

reg = pd.read_csv(OUT_DIR / "orb_regime_by_session.csv")
reg["date"] = pd.to_datetime(reg["date"])
reg = reg.sort_values("date").reset_index(drop=True)

pnl = pd.read_csv(OUT_DIR / "orb_trailing_pnl.csv")
feat = pd.read_csv(OUT_DIR / "orb_features_labels_1s.csv")[["date", "direction_up", "vpt_30"]]
t = pnl.merge(feat, on="date", how="left")
t["date"] = pd.to_datetime(t["date"])
vhi = t["vpt_30"].quantile(2/3)
t = t[(t.direction_up == 1.0) & (t.vpt_30 <= vhi)].copy()   # UP + anti-absorption
t["year"] = t["date"].dt.year


def yeartable(sub, col, label):
    print(f"  {label}")
    print(f"  {'year':>6} {'n':>4} {'t/mo':>5} {'WR%':>6} {'EVnet':>7} {'PF':>6}")
    for y in sorted(sub["year"].unique()) + ["ALL"]:
        g = sub if y == "ALL" else sub[sub.year == y]
        v = g[col].to_numpy()
        if len(v) == 0:
            print(f"  {str(y):>6} {0:>4}"); continue
        wins = v[v > 0].sum(); loss = -v[v < 0].sum()
        mo = g["date"].dt.to_period("M").nunique()
        print(f"  {str(y):>6} {len(v):>4} {len(v)/max(mo,1):>5.1f} {(v>0).mean()*100:>5.1f}% "
              f"{v.mean()-COMMISSION:>7.1f} {wins/loss if loss else float('inf'):>6.2f}")


col = "trail_40_20_40"
print("### BASELINE (no regime gate) — UP + anti-absorption")
yeartable(t, col, "baseline")

for K in (10, 20, 40):
    reg[f"trail_trendy_{K}"] = reg["trendiness"].shift(1).rolling(K, min_periods=K // 2).mean()
merged = t.merge(reg[["date"] + [f"trail_trendy_{K}" for K in (10, 20, 40)]], on="date", how="left")

for K in (10, 20, 40):
    tt = f"trail_trendy_{K}"
    thr = merged[tt].median()
    for mult, tag in [(1.0, "median"), (0.0, "any>0")]:
        gate = merged[merged[tt] >= (thr if tag == "median" else 0.0)]
        print(f"\n### GATE trailing trendiness K={K} >= {tag} ({thr:.2f} if median)")
        yeartable(gate, col, f"K={K} {tag}")
