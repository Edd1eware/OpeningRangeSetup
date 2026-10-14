"""Re-estimate the model's two weakest inputs on 26 years instead of 424 days.

The planning number in note 08 -- a modelled win rate of 0.5164 at a 94-point
stop, worth about three points of Lucid pass probability -- rests on three
inputs. One of them has 26 years behind it and two do not:

    drift      +0.1088% on window days, from NQ=F since 2000.  OK.
    sigma       1.1145%, from the 424 one-second sessions on disk, which are
                2021, part of 2022 and 2026 -- two strong bull years. A badly
                estimated sigma moves the win rate linearly, so this matters.
    resolution  the share of sessions whose path reaches the barrier before the
                bell, also from those 424 sessions.

Both of the weak ones can be estimated from DAILY bars over the full 26 years,
free, and more honestly:

    sigma       the standard deviation of the open-to-close return.
    resolution  a barrier b is reached when the day's high clears open*(1+b) or
                its low breaks open*(1-b). Daily high and low answer that
                exactly -- no intraday path needed, because the question is
                whether the extreme was reached at all, not when.

Reported for the whole history and for the last five years separately, because
volatility regime is the input most likely to have shifted, and the forward
plan should use the regime it will trade in rather than a 26-year average.
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


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SC = _load("sc48", "48_drift_condition_scan.py")

RISK_USD = 1500.0
MNQ_PER_POINT = 2.0
NQ_PER_POINT = 20.0
MNQ_COMM = 1.0
NQ_COMM = 4.0
TICK = 0.25
DRIFT_WINDOW_PCT = 0.1088
DRIFT_CONTROL_PCT = 0.0296


def p_up_first(mu, sigma, b):
    return 1.0 / (1.0 + np.exp(-2.0 * mu * b / sigma ** 2))


def main():
    d = SC.fetch("NQ=F")
    d["r_oc"] = (d.close / d.open - 1.0) * 100
    d["up_reach"] = (d.high / d.open - 1.0) * 100     # best case above the open
    d["dn_reach"] = (1.0 - d.low / d.open) * 100      # best case below it
    d["year"] = d.date.dt.year
    recent = d[d.year >= 2021]

    print(f"\nNQ=F daily, {len(d)} sessions {d.date.min().date()}..{d.date.max().date()}")
    print(f"{'sample':>16} {'n':>6} {'sigma_oc %':>11} {'median |r| %':>13} "
          f"{'median up reach':>16} {'median dn reach':>16}")
    for name, g in (("2000-2026", d), ("2021-2026", recent)):
        print(f"{name:>16} {len(g):>6} {g.r_oc.std(ddof=1):>11.4f} "
              f"{g.r_oc.abs().median():>13.4f} {g.up_reach.median():>16.4f} "
              f"{g.dn_reach.median():>16.4f}")
    print("\nfor comparison, the 424 one-second sessions on disk gave "
          "sigma 1.1145%")

    sig_all = float(d.r_oc.std(ddof=1))
    sig_rec = float(recent.r_oc.std(ddof=1))
    price = float(d.close.iloc[-1])
    print(f"\nlast close {price:,.2f}; the stop distance in PERCENT is what the "
          f"model needs, so the price level matters")

    configs = []
    for n in (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20):
        notional = n * MNQ_PER_POINT * price
        configs.append((f"{n} MNQ", n, MNQ_PER_POINT, MNQ_COMM, notional))
    for n in (1, 2):
        notional = n * NQ_PER_POINT * price
        configs.append((f"{n} NQ", n, NQ_PER_POINT, NQ_COMM, notional))

    rows = []
    for label, sigma, sample in (("26y", sig_all, d), ("5y", sig_rec, recent)):
        print(f"\n=== sigma = {sigma:.4f}% ({label} sample), resolution measured "
              f"on {len(sample)} daily highs and lows ===")
        print(f"{'position':>9} {'stop %':>7} {'stop pts':>9} {'resolve':>8} "
              f"{'WR win':>8} {'BE':>7} {'EV$ win':>9} {'EV$ ctrl':>9} {'edge$':>8}")
        for name, n, per_pt, comm, notional in configs:
            b = RISK_USD / notional * 100
            if b > 3.0:
                continue
            pts = b / 100 * price
            cost = comm * n + TICK * per_pt * n
            reach = float(((sample.up_reach >= b) | (sample.dn_reach >= b)).mean())
            pw = p_up_first(DRIFT_WINDOW_PCT, sigma, b)
            pc = p_up_first(DRIFT_CONTROL_PCT, sigma, b)
            ev_w = ((2 * pw - 1) * RISK_USD * reach
                    + (1 - reach) * (DRIFT_WINDOW_PCT / 100) * notional - cost)
            ev_c = ((2 * pc - 1) * RISK_USD * reach
                    + (1 - reach) * (DRIFT_CONTROL_PCT / 100) * notional - cost)
            be = 0.5 + cost / (2 * RISK_USD)
            print(f"{name:>9} {b:>7.3f} {pts:>9.1f} {reach:>8.1%} {pw:>8.4f} "
                  f"{be:>7.4f} {ev_w:>+9.2f} {ev_c:>+9.2f} {ev_w - ev_c:>+8.2f}")
            rows.append(dict(sigma_sample=label, sigma_pct=sigma, position=name,
                             contracts=n, notional=notional, stop_pct=b,
                             stop_points=pts, cost_usd=cost, resolve=reach,
                             wr_window=pw, breakeven=be, ev_window=ev_w,
                             ev_control=ev_c, edge_usd=ev_w - ev_c))
    res = pd.DataFrame(rows)
    res.to_csv(C.DATA / "reports" / "model_inputs_long_history.csv", index=False)

    print("\n=== the planning configuration, under both volatility regimes ===")
    for label in ("26y", "5y"):
        g = res[(res.sigma_sample == label) & (res.resolve >= 0.90)]
        if not len(g):
            continue
        best = g.loc[g.ev_window.idxmax()]
        print(f"  sigma {label}: {best.position}, stop {best.stop_points:.0f} pts "
              f"({best.stop_pct:.3f}%), resolves {best.resolve:.1%}, "
              f"WR {best.wr_window:.4f} vs BE {best.breakeven:.4f}, "
              f"EV ${best.ev_window:+.2f}, calendar edge ${best.edge_usd:+.2f}")
    print(f"\nwrote {C.DATA / 'reports' / 'model_inputs_long_history.csv'}")


if __name__ == "__main__":
    main()
