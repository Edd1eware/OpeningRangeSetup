# -*- coding: utf-8 -*-
"""Long-only ORB evaluation (DOWN is negative every year -> dropped).

Confirms the robust long-only edge across trailing/fixed managements, reports
account-level max drawdown ($, 1 contract) vs the Lucid 150k limit ($4,500),
then probes a second robust filter to rescue 2024, and a simple probability
sizing (1/2/3 contracts) that never enlarges risk in a losing regime.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")
COMMISSION_TICKS = 2.0
TICK_USD = 5.0
LUCID_DD = 4500.0

feat = pd.read_csv(OUT_DIR / "orb_features_labels_1s.csv")
pnl = pd.read_csv(OUT_DIR / "orb_trailing_pnl.csv")
mgmt_cols = [c for c in pnl.columns if c.startswith(("trail_", "fixed_"))]
df = feat.merge(pnl[["date"] + mgmt_cols], on="date", how="inner")
df["year"] = pd.to_datetime(df["date"]).dt.year
years = sorted(df["year"].unique())


def table(sub, col, title):
    print(f"=== {title}  [{col}] ===")
    print(f"{'year':>6} {'n':>4} {'t/mo':>5} {'WR%':>6} {'EVnet':>7} {'PF':>6} {'maxDD$':>8} {'net$':>9}")
    def row(g, label):
        p = g[col].to_numpy()
        if len(p) == 0:
            return
        net = p - COMMISSION_TICKS
        wins = p[p > 0].sum(); losses = -p[p < 0].sum()
        eq = np.cumsum(net * TICK_USD)
        dd = (np.maximum.accumulate(eq) - eq).max()
        mo = pd.to_datetime(g["date"]).dt.to_period("M").nunique()
        print(f"{label:>6} {len(p):>4} {len(p)/max(mo,1):>5.1f} {(p>0).mean()*100:>5.1f}% "
              f"{net.mean():>7.1f} {wins/losses if losses else float('inf'):>6.2f} "
              f"{dd:>8.0f} {eq[-1]:>9.0f}")
    for y in years:
        row(sub[sub.year == y], str(y))
    row(sub, "ALL")
    print()


up = df[df.direction_up == 1.0]

print("################ LONG-ONLY (UP breakouts) across managements ################\n")
for col in ["trail_40_20_40", "trail_50_20_40", "fixed_60_30", "fixed_60_60", "trail_50_20_30"]:
    table(up, col, "UP-only")

# second robust filter probe: keep UP, require moderate pre-breakout momentum
# (dir_30 in mid band) and non-extreme efficiency (vpt_30 not in top tercile).
print("################ UP + robust secondary filters ################\n")
d1, d2 = df["dir_30"].quantile([1/3, 2/3])
v2 = df["vpt_30"].quantile(2/3)
f_mom = up[(up.dir_30 > d1) & (up.dir_30 <= d2)]
table(f_mom, "trail_40_20_40", "UP & dir_30 MID")
f_eff = up[up.vpt_30 <= v2]
table(f_eff, "trail_40_20_40", "UP & vpt_30 not-HIGH")
f_both = up[(up.dir_30 > d1) & (up.dir_30 <= d2) & (up.vpt_30 <= v2)]
table(f_both, "trail_40_20_40", "UP & dir_30 MID & vpt_30 not-HIGH")

# simple sizing: base 1 contract on all UP; +1 on the best robust bucket.
print("################ SIZING (skip DOWN=0, UP base=1, best bucket=2) ################\n")
col = "trail_40_20_40"
up = up.copy()
up["size"] = 1
best = (up.dir_30 > d1) & (up.dir_30 <= d2)
up.loc[best, "size"] = 2
print(f"=== sized UP  [{col}] ===")
print(f"{'year':>6} {'trades':>7} {'contracts':>9} {'net$':>9} {'maxDD$':>8}")
for y in years + ["ALL"]:
    g = up if y == "ALL" else up[up.year == y]
    p = (g[col].to_numpy() - COMMISSION_TICKS) * g["size"].to_numpy() * TICK_USD
    eq = np.cumsum(p)
    dd = (np.maximum.accumulate(eq) - eq).max() if len(p) else 0
    print(f"{str(y):>6} {len(g):>7} {int(g['size'].sum()):>9} {eq[-1] if len(p) else 0:>9.0f} {dd:>8.0f}")
print(f"\nLucid DD limit ${LUCID_DD:.0f}")
