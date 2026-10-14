"""Is a 300-tick symmetric bracket actually a fair coin on real NQ sessions?

The taper policy of script 37 reaches a 43% pass probability on a 50K
evaluation with ZERO edge, and its whole arithmetic rests on one assumption:
that a symmetric K-tick bracket wins exactly half the time before cost, and
resolves inside the session. Both halves of that need checking against the
data rather than against theory, because both can fail:

    FAIRNESS    a martingale gives P(target first) = 1/2 for a symmetric
                bracket, but NQ is not exactly a martingale at 300 ticks, and
                the tie rule (ambiguous second charged to the stop) biases the
                measured rate DOWNWARD by construction.
    RESOLUTION  a 300-tick stop is 75 index points. If a meaningful share of
                trades is still open at 16:00, the policy is not "one trade a
                day, resolved": it either holds overnight through a gap or
                closes at market, and neither is the modelled payoff.

If the empirical win rate at K=300 comes out at, say, 0.47 rather than 0.50,
the 43% evaporates: the sweep in script 37 shows the pass probability is steep
in the win rate around this point. So this is not a formality.

Measured on the 150 sessions on disk, one entry per session at a fixed clock
time, several entry times reported so the answer does not hinge on one.
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

TICK = 0.25
COST_TICKS = 1.8
BRACKETS = (200, 240, 280, 300, 320, 360, 400)
ENTRY_TIMES = ("09:35", "10:00", "11:00", "13:00")
N_BOOT = 20000
SEED = 20261013


def one_trade(s, sec, k, side):
    """Outcome of a single bracket entered at `sec`, forced flat at 16:00.

    Returns (R, resolved) where R is +1 target, -1 stop, or the mark-to-market
    fraction if the session ended with the trade still open.
    """
    op, hi, lo, c, n = s["open"], s["high"], s["low"], s["close"], s["n"]
    e = sec + 1
    if e >= n:
        return np.nan, False
    entry = op[e]
    kk = k * TICK
    h_ = hi[e:]; l_ = lo[e:]
    if side > 0:
        m_tp = h_ >= entry + kk; m_sl = l_ <= entry - kk
    else:
        m_tp = l_ <= entry - kk; m_sl = h_ >= entry + kk
    INF = 1 << 30
    i_tp = int(np.argmax(m_tp)) if m_tp.any() else INF
    i_sl = int(np.argmax(m_sl)) if m_sl.any() else INF
    if i_tp == INF and i_sl == INF:
        return side * (c[n - 1] - entry) / kk, False
    if i_sl <= i_tp:
        return -1.0, True
    return 1.0, True


def main():
    bars = DS.load_bars()
    groups = dict(tuple(bars.groupby("session", sort=True)))
    sessions = sorted(groups)
    rng = np.random.default_rng(SEED)

    rows = []
    grids = {}
    for sess in track(sessions, label="session grids"):
        s = DS.session_grid(groups[sess])
        if s:
            grids[sess] = s

    print(f"\n{len(grids)} sessions\n")
    for et in ENTRY_TIMES:
        hh, mm = et.split(":")
        sec = (int(hh) * 3600 + int(mm) * 60) - (9 * 3600 + 30 * 60)
        print(f"=== entry at {et} ET ===")
        print(f"{'K':>5} {'n':>5} {'WR_long':>9} {'WR_short':>9} {'WR_both':>9} "
              f"{'unresolved':>11} {'EVnet_tk':>9} {'WR 95% CI':>18}")
        for k in BRACKETS:
            rl, rs, unres = [], [], 0
            for sess, s in grids.items():
                for side, bucket in ((+1, rl), (-1, rs)):
                    r, done = one_trade(s, sec, k, side)
                    if np.isnan(r):
                        continue
                    bucket.append(r)
                    if not done:
                        unres += 1
            rl = np.array(rl); rs = np.array(rs)
            both = np.concatenate([rl, rs])
            if len(both) < 20:
                continue
            wr = float((both > 0).mean())
            boot = np.array([(rng.choice(both, len(both), replace=True) > 0).mean()
                             for _ in range(2000)])
            lo, hi = np.percentile(boot, [2.5, 97.5])
            ev_net = float(both.mean() * k - COST_TICKS)
            print(f"{k:>5} {len(both):>5} {(rl>0).mean():>9.4f} {(rs>0).mean():>9.4f} "
                  f"{wr:>9.4f} {unres/max(len(both),1):>11.2%} {ev_net:>+9.2f} "
                  f"{f'[{lo:.4f},{hi:.4f}]':>18}")
            rows.append(dict(entry=et, bracket=k, n=len(both),
                             wr_long=float((rl > 0).mean()),
                             wr_short=float((rs > 0).mean()), wr=wr,
                             unresolved=unres / max(len(both), 1),
                             ev_net_ticks=ev_net, wr_lo=float(lo), wr_hi=float(hi)))
        print()

    df = pd.DataFrame(rows)
    df.to_csv(C.DATA / "reports" / "bracket_fairness.csv", index=False)

    print("=== the number the taper policy depends on ===")
    sub = df[df.bracket == 300]
    print(sub[["entry", "n", "wr", "wr_lo", "wr_hi", "unresolved", "ev_net_ticks"]]
          .round(4).to_string(index=False))
    print("\nscript 37 assumed WR 0.5000 and full intraday resolution at K=300.")
    print(f"wrote {C.DATA / 'reports' / 'bracket_fairness.csv'}")


if __name__ == "__main__":
    main()
