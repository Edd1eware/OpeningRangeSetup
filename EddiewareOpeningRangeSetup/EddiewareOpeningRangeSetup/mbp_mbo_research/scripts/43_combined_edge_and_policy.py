"""Putting the two halves together: a rare edge under the taper sizing policy.

The two results of this session do not combine the way either of them reads on
its own, and the reason is a constraint neither modelled.

    Note 03  the taper policy passes 43% of 50K evaluations with zero edge,
             assuming ONE TRADE EVERY DAY.
    Note 06  the turn-of-month effect, if real, exists on about THREE DAYS A
             MONTH.

A rule that only fires three times a month cannot feed a one-trade-a-day
policy. The trader either waits -- and then the evaluation takes months
instead of days -- or fills the other days with zero-edge trades, which dilutes
the win rate back toward 0.50 while still paying cost on every one.

This measures that trade-off directly, which is the question the objective
actually poses:

    is it better to trade ONLY the 3 edge days a month at a higher win rate,
    or EVERY day at a win rate diluted toward a coin flip?

Both arms use the same taper sizing, the same cost, the same Lucid 50K rules.
The only difference is how often the trader is allowed to bet and at what win
rate. MAX_DAYS becomes a real constraint in the sparse arm, so calendar time to
pass is reported alongside the probability: a policy that passes 60% of the
time but needs eight months is not obviously better than one that passes 43%
in a week, and the comparison belongs to the user, not to the script.
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


P37 = _load("p37", "37_lucid_policy_search.py")

TICK_USD = 5.0
START = 50_000.0
TARGET = 53_000.0
DD = 2_000.0
LOCK_AT = 52_100.0
LOCK_FLOOR = 50_100.0
MAX_CAL_DAYS = 500            # a hard horizon so a sparse arm cannot run forever
N_SIM = 40_000
SEED = 20261013

TRADING_DAYS_PER_MONTH = 21
EDGE_DAYS_PER_MONTH = 3       # the +1,+2,+3 window


def simulate(wr_edge, wr_filler, cap, cost_ticks, trade_every_day,
             consistency, daily_loss, n_sim, rng):
    """Taper sizing, but betting only on edge days unless told otherwise.

    An edge day arrives every TRADING_DAYS_PER_MONTH / EDGE_DAYS_PER_MONTH
    sessions. In the dense arm the other days are traded too, at wr_filler.
    """
    cost_usd = cost_ticks * TICK_USD
    bal = np.full(n_sim, START)
    floor = np.full(n_sim, START - DD)
    locked = np.zeros(n_sim, dtype=bool)
    best_day = np.zeros(n_sim)
    alive = np.ones(n_sim, dtype=bool)
    passed = np.zeros(n_sim, dtype=bool)
    days_used = np.zeros(n_sim, dtype=int)
    n_trades = np.zeros(n_sim, dtype=int)

    period = TRADING_DAYS_PER_MONTH / EDGE_DAYS_PER_MONTH
    for day in range(1, MAX_CAL_DAYS + 1):
        if not alive.any():
            break
        is_edge = (day % round(period)) < 1
        if not (is_edge or trade_every_day):
            continue
        wr = wr_edge if is_edge else wr_filler
        day_start = bal.copy()
        to_target = np.maximum(TARGET - bal, 1.0)
        risk = np.clip(np.minimum(to_target, cap), 50.0, cap)
        win = rng.random(n_sim) < wr
        pnl = np.where(win, risk, -risk) - cost_usd
        bal = np.where(alive, bal + pnl, bal)
        n_trades += alive
        hit = alive & (bal <= floor)
        alive &= ~hit

        best_day = np.where(alive, np.maximum(best_day, bal - day_start), best_day)
        reach = alive & ~locked & (bal >= LOCK_AT)
        floor = np.where(reach, LOCK_FLOOR, floor)
        locked |= reach
        trail = alive & ~locked
        floor = np.where(trail, np.maximum(floor, bal - DD), floor)

        at_t = alive & (bal >= TARGET)
        ok = at_t & (best_day <= consistency * (bal - START) + 1e-9)
        passed |= ok
        days_used = np.where(ok & (days_used == 0), day, days_used)
        alive &= ~ok

    return dict(p_pass=float(passed.mean()),
                median_cal_days=float(np.median(days_used[passed])) if passed.any() else np.nan,
                p90_cal_days=float(np.percentile(days_used[passed], 90)) if passed.any() else np.nan,
                median_trades=float(np.median(n_trades[passed])) if passed.any() else np.nan)


def main():
    rng = np.random.default_rng(SEED)
    rows = []

    # the edge-day win rate is not known yet; the NQ verdict is pending, so the
    # whole plausible range is reported rather than one guess
    EDGE_WRS = (0.50, 0.53, 0.55, 0.57, 0.60, 0.65)
    CAPS = (1400.0, 1500.0)

    print("=== SPARSE: trade ONLY the ~3 edge days a month ===")
    print(f"{'WR_edge':>8} {'cap$':>6} {'P(pass)':>9} {'median days':>12} "
          f"{'p90 days':>9} {'trades':>7}")
    for wr in EDGE_WRS:
        for cap in CAPS:
            r = simulate(wr, 0.0, cap, 1.8, False, 0.50, None, N_SIM, rng)
            print(f"{wr:>8.2f} {cap:>6.0f} {r['p_pass']:>9.4f} "
                  f"{r['median_cal_days']:>12.0f} {r['p90_cal_days']:>9.0f} "
                  f"{r['median_trades']:>7.0f}")
            rows.append(dict(arm="sparse", wr_edge=wr, wr_filler=np.nan,
                             cap=cap, **r))

    print("\n=== DENSE: trade every day, edge days at WR_edge, the rest at 0.50 ===")
    print(f"{'WR_edge':>8} {'cap$':>6} {'P(pass)':>9} {'median days':>12} "
          f"{'p90 days':>9} {'trades':>7}")
    for wr in EDGE_WRS:
        for cap in CAPS:
            r = simulate(wr, 0.50, cap, 1.8, True, 0.50, None, N_SIM, rng)
            print(f"{wr:>8.2f} {cap:>6.0f} {r['p_pass']:>9.4f} "
                  f"{r['median_cal_days']:>12.0f} {r['p90_cal_days']:>9.0f} "
                  f"{r['median_trades']:>7.0f}")
            rows.append(dict(arm="dense", wr_edge=wr, wr_filler=0.50,
                             cap=cap, **r))

    print("\n=== DENSE but the filler is slightly NEGATIVE, WR 0.48 ===")
    print("(every rule this project tested came back slightly negative after "
          "cost, so this is the realistic filler, not 0.50)")
    print(f"{'WR_edge':>8} {'cap$':>6} {'P(pass)':>9} {'median days':>12}")
    for wr in EDGE_WRS:
        r = simulate(wr, 0.48, 1500.0, 1.8, True, 0.50, None, N_SIM, rng)
        print(f"{wr:>8.2f} {1500:>6.0f} {r['p_pass']:>9.4f} "
              f"{r['median_cal_days']:>12.0f}")
        rows.append(dict(arm="dense_neg_filler", wr_edge=wr, wr_filler=0.48,
                         cap=1500.0, **r))

    df = pd.DataFrame(rows)
    df.to_csv(C.DATA / "reports" / "combined_edge_policy.csv", index=False)

    print("\n=== the comparison that decides ===")
    for wr in EDGE_WRS:
        s = df[(df.arm == "sparse") & (df.wr_edge == wr) & (df.cap == 1500)]
        d = df[(df.arm == "dense") & (df.wr_edge == wr) & (df.cap == 1500)]
        n = df[(df.arm == "dense_neg_filler") & (df.wr_edge == wr)]
        if not len(s) or not len(d):
            continue
        print(f"  WR_edge {wr:.2f}: sparse {s.p_pass.iloc[0]:.4f} in "
              f"{s.median_cal_days.iloc[0]:.0f} days | dense(filler .50) "
              f"{d.p_pass.iloc[0]:.4f} in {d.median_cal_days.iloc[0]:.0f} | "
              f"dense(filler .48) {n.p_pass.iloc[0]:.4f}")
    print(f"\nwrote {C.DATA / 'reports' / 'combined_edge_policy.csv'}")


if __name__ == "__main__":
    main()
