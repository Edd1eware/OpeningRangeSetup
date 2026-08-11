# -*- coding: utf-8 -*-
"""Monte Carlo: probability of passing a Lucid eval in <=3 months.

WR is capped ~45-55% on price/volume data, so the objective shifts to: size the
robust long-only ORB engine to reach the profit target before the trailing
drawdown busts, inside a 3-month window. Frequency is the key lever - more
trades let you use smaller size and survive the trailing DD.

Method: build the real chronological net-tick trade stream of a setup, then
block-bootstrap 3-month sequences (blocks preserve losing streaks, and the
sample includes the bad 2024 regime). For each contract size and account we
report P(pass), P(bust), P(timeout).

Lucid rules assumed (EDIT if yours differ):
  100k -> target +$6,000, trailing MaxDD $3,000
  150k -> target +$9,000, trailing MaxDD $4,500   (150k DD from user memory)
Trailing DD modelled on the closed-trade equity peak (intraday unreal. ignored).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")
TICK_USD = 5.0
COMMISSION_TICKS = 2.0
BLOCK = 8
N_SIMS = 20000
RNG = np.random.default_rng(11)

ACCOUNTS = {"100k": (6000.0, 3000.0), "150k": (9000.0, 4500.0)}

pnl = pd.read_csv(OUT_DIR / "orb_trailing_pnl.csv")
feat = pd.read_csv(OUT_DIR / "orb_features_labels_1s.csv")[["date", "direction_up", "vpt_30"]]
df = pnl.merge(feat, on="date", how="left").sort_values("date").reset_index(drop=True)
vhi = df["vpt_30"].quantile(2/3)

SETUPS = {
    # name -> (mask, trades/month, mgmt column)
    "UP-only (9/mo, PF1.35)": (df.direction_up == 1.0, 9.0, "trail_40_20_40"),
    "UP+filter (6.3/mo, PF1.55)": ((df.direction_up == 1.0) & (df.vpt_30 <= vhi), 6.3, "trail_40_20_40"),
}


def net_series(mask, col):
    s = df.loc[mask, col].to_numpy()
    return s - COMMISSION_TICKS  # net ticks per trade, 1 contract


def block_boot(series, n):
    out = []
    while len(out) < n:
        i = RNG.integers(0, len(series))
        out.extend(series[i:i + BLOCK])
    return np.asarray(out[:n])


def simulate(series, n_trades, size, target, dd):
    """Return 'pass' / 'bust' / 'timeout' for one 3-month sequence."""
    seq = block_boot(series, n_trades) * size * TICK_USD
    eq = 0.0
    peak = 0.0
    for pnl_usd in seq:
        eq += pnl_usd
        peak = max(peak, eq)
        if peak - eq >= dd:
            return "bust"
        if eq >= target:
            return "pass"
    return "timeout"


def main():
    for sname, (mask, fmo, col) in SETUPS.items():
        series = net_series(mask, col)
        n_trades = int(round(fmo * 3))
        ev = series.mean() * TICK_USD
        print(f"\n================ {sname} ================")
        print(f"trades/3mo={n_trades} | EVnet/trade=${ev:.1f} (1ct) | WR={ (series>0).mean()*100:.1f}%")
        for acc, (target, dd) in ACCOUNTS.items():
            print(f"\n  --- Lucid {acc}: target +${target:.0f}, trailing DD ${dd:.0f} ---")
            print(f"  {'size':>4} {'pass%':>6} {'bust%':>6} {'timeout%':>8} {'maxLoss1':>9}")
            best = (None, -1)
            for size in range(1, 16):
                res = [simulate(series, n_trades, size, target, dd) for _ in range(N_SIMS)]
                res = np.array(res)
                pp = (res == "pass").mean() * 100
                bb = (res == "bust").mean() * 100
                tt = (res == "timeout").mean() * 100
                worst1 = -series.min() * size * TICK_USD  # $ of the single worst trade
                if pp > best[1]:
                    best = (size, pp)
                print(f"  {size:>4} {pp:>5.1f}% {bb:>5.1f}% {tt:>7.1f}% {worst1:>9.0f}")
            print(f"  -> best size = {best[0]} contracts, P(pass 3mo) = {best[1]:.1f}%")

    # frequency sensitivity: what if we had k x the trades (same distribution)?
    print("\n================ FREQUENCY SENSITIVITY (150k, best size per case) ================")
    mask, _, col = SETUPS["UP+filter (6.3/mo, PF1.55)"]
    series = net_series(mask, col)
    target, dd = ACCOUNTS["150k"]
    print(f"{'trades/mo':>10} {'bestSize':>9} {'pass%':>6}")
    for fmo in (6.3, 12, 20, 40):
        n_trades = int(round(fmo * 3))
        best = (None, -1)
        for size in range(1, 16):
            res = np.array([simulate(series, n_trades, size, target, dd) for _ in range(N_SIMS // 2)])
            pp = (res == "pass").mean() * 100
            if pp > best[1]:
                best = (size, pp)
        print(f"{fmo:>10.1f} {best[0]:>9} {best[1]:>5.1f}%")
    print("\n(higher frequency -> smaller size -> survive DD -> higher pass odds)")


if __name__ == "__main__":
    main()
