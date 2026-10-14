"""From a daily drift to a bracket's edge, with the arithmetic done properly.

The mistake this corrects
-------------------------
Script 45 measured, on 69 turn-of-month sessions, a bracket edge that was
negative at K = 150, 200 and 250 and strongly positive at K = 300 and 400. I
read the inconsistency as a red flag, on the reasoning that a real directional
drift should show up at every bracket size. That reasoning was wrong.

For a Brownian path with daily drift mu and daily volatility sigma, symmetric
barriers at plus and minus b give

    P(up barrier first) = 1 / (1 + exp(-2*mu*b / sigma^2))

and for a small drift that is approximately 0.5 + mu*b / (2*sigma^2), so

    gross edge in ticks  =  (2P - 1) * k  ~  mu * k^2 * tick^2 / (sigma^2 * S^2)

The gross edge grows with the SQUARE of the bracket while the cost stays flat
at 1.8 ticks. Small brackets therefore cannot clear the cost no matter how real
the drift is, and the sign pattern script 45 found is what the theory predicts
rather than evidence against it.

The uncomfortable consequence
-----------------------------
The same arithmetic says a +0.1% daily drift is worth only about four net
ticks at K=300, not the +56 that 69 sessions reported. The measurement is
noise around a small true value, and the small true value is the one to plan
with. This script computes it from the long-history drift and the measured
volatility, so the number that feeds the Lucid policy is the defensible one
rather than the flattering one.

Everything here is a model, and the model's own assumptions are listed where
they bite: constant drift through the session, constant volatility, no
intraday mean reversion, continuous monitoring, fills at the barrier. Real
sessions violate all five, which is why the empirical check at the end
compares the model's prediction against what the 1s bars actually did on the
non-window days, where the sample is large enough to mean something.
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
BRACKETS = (100, 150, 200, 250, 300, 400, 500)
# daily open-to-close drift on window days, percent, from the long histories
DRIFTS = {
    "^GSPC 1962-2026 window": 0.1005,
    "^NDX 1985-2026 window": 0.1461,
    "NQ=F 2000-2026 window": 0.1088,
    "SPY 1993-2026 window": 0.0824,
    "NQ=F non-window (control)": 0.0296,
}


def p_up_first(mu: float, sigma: float, b: float) -> float:
    """P(+b touched before -b) for Brownian motion with drift, exact."""
    x = 2.0 * mu * b / (sigma ** 2)
    return 1.0 / (1.0 + np.exp(-x))


def main():
    bars = DS.load_bars()
    rows = []
    for sess, g in track(list(bars.groupby("session", sort=True)), label="sessions"):
        s = DS.session_grid(g)
        if not s:
            continue
        op = float(s["open"][0]); cl = float(s["close"][-1])
        rows.append(dict(session=pd.Timestamp(sess), px_open=op,
                         r_oc_pct=(cl / op - 1.0) * 100))
    d = pd.DataFrame(rows)
    sigma = float(d.r_oc_pct.std(ddof=1))
    px = float(d.px_open.median())
    print(f"\n{len(d)} sessions. Daily open-to-close sigma = {sigma:.4f}%, "
          f"median price {px:,.0f}\n")

    print("=== model: net ticks per trade, by drift and bracket ===")
    print("(a bracket of k ticks is b = k * 0.25 / price in return terms)")
    hdr = f"{'drift %':>28} " + "".join(f"{'K'+str(k):>9}" for k in BRACKETS)
    print(hdr)
    out = []
    for name, mu_pct in DRIFTS.items():
        cells = []
        for k in BRACKETS:
            b = k * TICK / px * 100          # barrier in percent, same units as mu
            p = p_up_first(mu_pct, sigma, b)
            gross = (2 * p - 1) * k
            cells.append(gross - COST_TICKS)
            out.append(dict(source=name, drift_pct=mu_pct, bracket=k,
                            p_up_first=p, gross_ticks=gross,
                            net_ticks=gross - COST_TICKS,
                            breakeven_wr=(k + COST_TICKS) / (2 * k)))
        print(f"{name:>28} " + "".join(f"{c:>+9.2f}" for c in cells))

    res = pd.DataFrame(out)
    res.to_csv(C.DATA / "reports" / "drift_to_bracket_theory.csv", index=False)

    print("\n=== the win rate the Lucid policy would actually see ===")
    print(f"{'drift %':>28} " + "".join(f"{'K'+str(k):>9}" for k in BRACKETS))
    for name, mu_pct in DRIFTS.items():
        cells = [p_up_first(mu_pct, sigma, k * TICK / px * 100) for k in BRACKETS]
        print(f"{name:>28} " + "".join(f"{c:>9.4f}" for c in cells))
    print(f"{'breakeven':>28} " +
          "".join(f"{(k + COST_TICKS) / (2 * k):>9.4f}" for k in BRACKETS))

    print("\n=== model check against the data, on NON-window days ===")
    print("(the control sample is large, so the model can be falsified here)")
    bars_by = {pd.Timestamp(k): v for k, v in bars.groupby("session", sort=True)}
    d["year"] = d.session.dt.year
    d["month"] = d.session.dt.month
    gg = d.groupby([d.year, d.month])
    d["tdom"] = gg.cumcount() + 1
    d["tdom_rev"] = gg.cumcount(ascending=False) + 1
    d["tom"] = d.tdom.le(3) & ~d.tdom_rev.eq(1)
    mu_ctrl = float(d.loc[~d.tom, "r_oc_pct"].mean())
    print(f"measured non-window drift on these {int((~d.tom).sum())} sessions: "
          f"{mu_ctrl:+.4f}%")
    meas = {k: [] for k in BRACKETS}
    for sess in track(d.loc[~d.tom, "session"], label="control brackets"):
        g = bars_by.get(pd.Timestamp(sess))
        s = DS.session_grid(g) if g is not None else None
        if not s:
            continue
        op = s["open"][0]; hi = s["high"]; lo = s["low"]; cl = s["close"][-1]
        for k in BRACKETS:
            kk = k * TICK
            m_tp = hi >= op + kk; m_sl = lo <= op - kk
            INF = 1 << 30
            i_tp = int(np.argmax(m_tp)) if m_tp.any() else INF
            i_sl = int(np.argmax(m_sl)) if m_sl.any() else INF
            if i_tp == INF and i_sl == INF:
                meas[k].append((cl - op) / kk)
            else:
                meas[k].append(1.0 if i_tp < i_sl else -1.0)
    print(f"\n{'K':>6} {'model net tk':>13} {'measured net tk':>16} {'n':>6}")
    for k in BRACKETS:
        b = k * TICK / px * 100
        model = (2 * p_up_first(mu_ctrl, sigma, b) - 1) * k - COST_TICKS
        arr = np.array(meas[k])
        print(f"{k:>6} {model:>+13.2f} {arr.mean() * k - COST_TICKS:>+16.2f} "
              f"{len(arr):>6}")
    print(f"\nwrote {C.DATA / 'reports' / 'drift_to_bracket_theory.csv'}")


if __name__ == "__main__":
    main()
