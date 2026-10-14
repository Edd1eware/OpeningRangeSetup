"""Separate the bracket from the horizon. My own script 30 confounded them.

Script 30 compared K=20/40 against K=80/150 and found the gross tick edge
jumping from ~0.35 ticks to ~4 and then ~18. That comparison is not clean,
because three things changed between the two runs at once:

    bracket   20/40            ->  80/150
    timeout   1800 s (30 min)  ->  10800 s (3 h)
    grid      every 60 s       ->  every 300 s

So the jump is attributable to any of the three, or to their interaction, and
the most likely culprit is not the bracket at all. A 3-hour label with a
5-minute grid makes the ~41 decisions in one session share nearly the same
forward window, which collapses the effective sample to the number of sessions
and lets a handful of trending days dominate.

This script builds ONE dataset on ONE grid with ONE timeout, and varies only K
across 20, 40, 80 and 150. That is the only way the scaling question has an
answer. Everything else is held exactly as script 30 had it for the big
brackets, so the K=80/150 numbers should reproduce.

Reading, fixed in advance
-------------------------
* a smooth rise in gross ticks across all four K -> the edge is proportional
  to the horizon the bracket implies, and script 30's jump was real.
* K=20/40 near zero and K=80/150 large, with nothing in between -> the effect
  is not about the bracket. It belongs to the long horizon and the overlap it
  creates, and the audit in script 31 is the one that decides it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as C
from progress import track


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DS = _load("ds26", "26_rth_ml_dataset.py")
BIG = _load("bg30", "30_bracket_scaling.py")

ALL_K = (20, 40, 80, 150)
COST_TICKS = 1.8
PATH = C.DATA / "features" / "rth_allk_3h.parquet"


def build():
    bars = DS.load_bars()
    groups = dict(tuple(bars.groupby("session", sort=True)))
    rows = []
    for sess in track(sorted(groups), label="all-K 3h labels"):
        s = DS.session_grid(groups[sess])
        if not s:
            continue
        hi_sec = min(BIG.DEC_TO, s["n"] - BIG.TIMEOUT_S - 2)
        if hi_sec <= BIG.DEC_FROM:
            continue
        dec = np.arange(BIG.DEC_FROM, hi_sec, BIG.GRID_S)
        f = DS.build_features(s, dec)
        f.insert(0, "session", pd.Timestamp(sess))
        f.insert(1, "sec", dec)
        for k in ALL_K:
            f[f"R_long_{k}"] = BIG.label_side_long_timeout(s, dec, k, +1)
            f[f"R_short_{k}"] = BIG.label_side_long_timeout(s, dec, k, -1)
        rows.append(f)
    df = pd.concat(rows, ignore_index=True)
    return df.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)


def main():
    if PATH.exists():
        df = pd.read_parquet(PATH)
        print(f"reusing {PATH}")
    else:
        df = build()
        df.to_parquet(PATH, index=False)
    print(f"dataset {df.shape}, {df.session.nunique()} sessions\n", flush=True)

    labels = [c for c in df.columns if c.startswith("R_")]
    feats = [c for c in df.columns if c not in labels + ["session", "sec"]]

    rows = []
    print(f"{'K':>5} {'side':>6} {'n':>5} {'sess':>5} {'WR':>7} {'gross_tk':>9} "
          f"{'net_tk':>8} {'base_tk':>8} {'gross_R':>8}")
    for k in ALL_K:
        for side in ("long", "short"):
            col = f"R_{side}_{k}"
            sel, base = BIG.walk(df, feats, col)
            g = sel.mean() * k
            print(f"{k:>5} {side:>6} {len(sel):>5} {'':>5} {(sel>0).mean():>7.4f} "
                  f"{g:>+9.3f} {g-COST_TICKS:>+8.3f} {base.mean()*k:>+8.3f} "
                  f"{sel.mean():>+8.4f}")
            rows.append(dict(bracket=k, side=side, n=len(sel),
                             wr=float((sel > 0).mean()),
                             ev_gross_ticks=float(g),
                             ev_net_ticks=float(g - COST_TICKS),
                             ev_gross_r=float(sel.mean()),
                             baseline_ticks=float(base.mean() * k)))
    out = pd.DataFrame(rows)
    out.to_csv(C.DATA / "reports" / "isolate_bracket_vs_horizon.csv", index=False)
    print(f"\nwrote {C.DATA / 'reports' / 'isolate_bracket_vs_horizon.csv'}")


if __name__ == "__main__":
    main()
