"""Borrowing power: estimate DIRECTION on 64 years, and the BRACKET on 1s bars.

The problem this solves
-----------------------
The turn-of-month candidate needs a win rate measured against a breakeven of
0.5030. Script 41 got 0.5778 out of sample on NQ, which is the right sign and
fails its significance bar at p = 0.1967. Worse, the arithmetic says it will
keep failing: separating 0.578 from 0.503 at a Bonferroni-corrected 0.0125
needs roughly 280 window days, and even the completed 2021-2025 download only
yields about 140. More NQ seconds cannot fix a daily-frequency sample size.

So stop trying. The quantity that needs a long sample and the quantity that
needs 1-second data are DIFFERENT quantities, and they can be estimated
separately and composed:

    DIRECTION   P(close > open) on window days. Needs decades, needs no
                intraday data at all, and is already measured: 64 years of
                ^GSPC at p = 0.0001, 41 of ^NDX, 26 of NQ futures.
    CONVERSION  P(a 300-tick long bracket wins | the day closed up) and the
                same given the day closed down. Needs the 1-second path but
                NOT a long sample, because it is a property of the bracket
                against intraday volatility, not of the calendar. It can be
                estimated on EVERY session on disk, window day or not, which
                is hundreds of observations instead of dozens.

Then the bracket win rate on window days is

    WR_bracket = P(up) * P(win | up) + (1 - P(up)) * P(win | down)

with P(up) taken from the long history and the conditionals from the 1s bars.
The composition is only valid if the conversion is STABLE -- if it does not
itself depend on the calendar -- so that is tested here rather than assumed:
the conditionals are computed separately on window days and on all other days,
and if they differ materially the whole approach is void and this script says
so instead of reporting a number.
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
BRACKETS = (150, 200, 250, 300, 400)
SEED = 20261013
# P(close > open) on window days, measured on the long histories by script 44
LONG_HISTORY_PUP = {
    "^GSPC 1962-2026": 0.5613,
    "^NDX 1985-2026": 0.5761,
    "NQ=F 2000-2026": 0.5584,
    "SPY 1993-2026": 0.5704,
}


def main():
    bars = DS.load_bars()
    rows = []
    for sess, g in track(list(bars.groupby("session", sort=True)),
                         label="sessions"):
        s = DS.session_grid(g)
        if not s:
            continue
        op = float(s["open"][0]); cl = float(s["close"][-1])
        hi, lo, c = s["high"], s["low"], s["close"]
        r = dict(session=pd.Timestamp(sess), up=cl > op,
                 r_oc_pct=(cl / op - 1.0) * 100)
        for k in BRACKETS:
            kk = k * TICK
            m_tp = hi >= op + kk
            m_sl = lo <= op - kk
            INF = 1 << 30
            i_tp = int(np.argmax(m_tp)) if m_tp.any() else INF
            i_sl = int(np.argmax(m_sl)) if m_sl.any() else INF
            if i_tp == INF and i_sl == INF:
                # Marked TO MARKET, not to the day's direction. Scoring an
                # unresolved day as a win whenever the close beat the open
                # hands the trade the day's direction for free, and the
                # control column showed exactly that: at K=300, where 7.3% of
                # days do not resolve, a fair coin produced a win rate of
                # 0.509 instead of 0.500, while K=150 with 0.7% unresolved
                # produced 0.4999. The bias was the handling, not the market.
                r[f"R{k}"] = (cl - op) / kk
                r[f"unres{k}"] = True
            else:
                r[f"R{k}"] = 1.0 if i_tp < i_sl else -1.0
                r[f"unres{k}"] = False
        rows.append(r)

    d = pd.DataFrame(rows)
    d["year"] = d.session.dt.year
    d["month"] = d.session.dt.month
    gg = d.groupby([d.year, d.month])
    d["tdom"] = gg.cumcount() + 1
    d["tdom_rev"] = gg.cumcount(ascending=False) + 1
    d["tom"] = d.tdom.le(3) & ~d.tdom_rev.eq(1)
    print(f"\n{len(d)} sessions, {int(d.tom.sum())} window days, "
          f"{d.session.min().date()} .. {d.session.max().date()}\n")

    print("=== CONVERSION: P(bracket long wins | day direction), ALL sessions ===")
    print(f"{'K':>5} {'n_up':>6} {'E[R|up]':>10} {'n_dn':>6} {'E[R|dn]':>10} "
          f"{'unresolved':>11} {'E[R] if P(up)=.5':>17}")
    conv = {}
    for k in BRACKETS:
        up = d.loc[d.up, f"R{k}"]
        dn = d.loc[~d.up, f"R{k}"]
        # expected R, not a win rate: R is +1, -1, or the mark-to-market
        # fraction, so the mean is the honest conditional payoff
        pu, pd_ = float(up.mean()), float(dn.mean())
        conv[k] = (pu, pd_)
        print(f"{k:>5} {len(up):>6} {pu:>10.4f} {len(dn):>6} {pd_:>10.4f} "
              f"{d[f'unres{k}'].mean():>11.2%} {0.5*pu + 0.5*pd_:>17.4f}")

    print("\n=== STABILITY: is the conversion the same on window days? ===")
    print("(if it is not, the composition below is invalid and must be dropped)")
    print(f"{'K':>5} {'E[R|up] tom':>14} {'non-tom':>9} {'E[R|dn] tom':>14} "
          f"{'non-tom':>9}")
    ok = True
    for k in BRACKETS:
        a = float(d.loc[d.tom & d.up, f"R{k}"].mean())
        b = float(d.loc[~d.tom & d.up, f"R{k}"].mean())
        cc = float(d.loc[d.tom & ~d.up, f"R{k}"].mean())
        e = float(d.loc[~d.tom & ~d.up, f"R{k}"].mean())
        print(f"{k:>5} {a:>14.4f} {b:>9.4f} {cc:>14.4f} {e:>9.4f}")
        if abs(a - b) > 0.12 or abs(cc - e) > 0.12:
            ok = False
    print(f"conversion stable across the calendar: {'YES' if ok else 'NO'}")

    print("\n=== COMPOSITION: bracket WR implied by the long-history direction ===")
    be = {k: (k + COST_TICKS) / (2 * k) for k in BRACKETS}
    out = []
    for src, pup in LONG_HISTORY_PUP.items():
        line = []
        for k in BRACKETS:
            pu, pd_ = conv[k]
            er = pup * pu + (1 - pup) * pd_
            line.append(er)
            out.append(dict(direction_source=src, p_up=pup, bracket=k,
                            er_up=pu, er_dn=pd_, er_implied=er,
                            ev_gross_ticks=er * k,
                            ev_net_ticks=er * k - COST_TICKS))
        print(f"  {src:18} P(up)={pup:.4f} -> " +
              "  ".join(f"K{k}:{w*k:+.1f}tk" for k, w in zip(BRACKETS, line)))
    print("  (gross ticks per trade; the cost to beat is "
          f"{COST_TICKS} ticks)")

    res = pd.DataFrame(out)
    res.to_csv(C.DATA / "reports" / "direction_to_bracket.csv", index=False)

    print("\n=== implied net EV in ticks per trade ===")
    piv = res.pivot_table(index="direction_source", columns="bracket",
                          values="ev_net_ticks")
    print(piv.round(2).to_string())
    print("\nand the measured baseline, all non-window days, for comparison:")
    for k in BRACKETS:
        w = float(d.loc[~d.tom, f"R{k}"].mean())
        t = float(d.loc[d.tom, f"R{k}"].mean())
        print(f"  K{k}: non-window E[R] {w:+.4f} ({w*k - COST_TICKS:+.2f} tk net) | "
              f"window E[R] {t:+.4f} ({t*k - COST_TICKS:+.2f} tk net)")
    print(f"\nwrote {C.DATA / 'reports' / 'direction_to_bracket.csv'}")


if __name__ == "__main__":
    main()
