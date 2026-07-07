"""Parity check: does 12_KillSwitchSizer.cs reproduce the validated design?

Reimplements the C# KillSwitchSizer EXACTLY (integer tiers full=base / half=round(base/2)
/ min=1, and the C# ordering: balance/dd updated, tier decided from the PRE-trade streak,
streak updated AFTER) and runs it over the same real 2025-2026 trade sequence that
kill_switch_sim.py uses. Then diffs net / maxDD / per-trade contracts against the sim's
run_killswitch (fractional tiers [1.0, 0.5, 0.25], streak updated BEFORE tier decision).

Purpose: catch port bugs (integer rounding, decision ordering) before spending an ATAS
replay. Run: python -u kill_switch_parity.py --base 3
"""
from __future__ import annotations

import argparse
import glob
import os
import numpy as np
import pandas as pd

TICK_USD = 5.0
CUSHION = 4500.0
OUT = (r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
       r"\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs\X10_R1")


def load_daily_ticks() -> pd.DataFrame:
    rows = []
    for f in sorted(glob.glob(os.path.join(OUT, "score_trade_result_*_NY.csv"))):
        try:
            d = pd.read_csv(f)
            if d.empty:
                continue
            d = d.iloc[0]
            lbl = str(d["Result_Label"]).upper()
            t = str(d["result TP SL BE"]).replace("+", "")
            tk = float(t) if t not in ("", "nan") else 0.0
            traded = lbl in ("TP", "SL", "BE")
            rows.append((str(d["fecha"]), traded, tk if traded else 0.0))
        except Exception:  # noqa: BLE001
            pass
    df = pd.DataFrame(rows, columns=["fecha", "traded", "ticks"]).drop_duplicates("fecha")
    df["date"] = pd.to_datetime(df["fecha"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


# ── Engine A: FAITHFUL C# port (integer tiers, CORRECTED streak-before order) ──
# Mirrors the DEPLOYED 12_KillSwitchSizer.cs (fix 2026-07-07: streak/green updated
# before the tier decision, so the streak override no longer lags one trade).
def run_csharp(traded, ticks, base, f1=0.35, f2=0.60, s_half=3, s_pause=4,
               rearm_green=2, probe_days=8):
    """Mirror KillSwitchSizer.OnTradeClosed + CurrentSize exactly.

    C# flow per real trade i:
      size_i = CurrentSize (tier set by OnTradeClosed(i-1))   <- read BEFORE entry
      trade i closes -> OnTradeClosed(pnl_i):
        balance += pnl_i; peak = max
        streak/green updated from pnl_i        (CORRECTED: before tier decision)
        dd = peak-balance; tier decided from dd and the updated streak
    """
    half = max(1, round(base / 2))     # C#: Math.Round(base/2, AwayFromZero)
    levels = [base, half, 1]           # full, half, min (integers)

    tier = 0
    streak = 0
    green = 0
    stuck = 0
    balance = 0.0
    peak = 0.0

    eq_path, sizes, tiers = [], [], []
    for i in range(len(ticks)):
        size_i = levels[tier]          # size used for THIS entry (set by prev OnTradeClosed)
        sizes.append(size_i)
        tiers.append(tier)

        # --- OnTradeClosed(pnl_i) ---
        pnl = ticks[i] * size_i * TICK_USD if traded[i] else 0.0
        balance += pnl
        if balance > peak:
            peak = balance
        # streak bookkeeping BEFORE tier decision (corrected C# order)
        if traded[i]:
            if pnl < 0:
                streak += 1; green = 0
            elif pnl > 0:
                streak = 0; green += 1
        dd = peak - balance
        dd_ti = 0 if dd < f1 * CUSHION else (1 if dd < f2 * CUSHION else 2)
        streak_ti = 2 if streak >= s_pause else (1 if streak >= s_half else 0)
        target = max(dd_ti, streak_ti)
        if target > tier:
            tier = target; green = 0; stuck = 0
        elif target < tier and (green >= rearm_green or stuck >= probe_days):
            tier -= 1; green = 0; stuck = 0
        else:
            stuck += 1

        eq_path.append(balance)

    eq = np.array(eq_path)
    dd = (eq - np.maximum.accumulate(eq)).min()
    return eq, dd, np.array(sizes), np.array(tiers)


# ── Engine B: the sim's run_killswitch (integer tiers, streak-before) ──────────
# Mirrors kill_switch_sim.py AFTER it was closed to integer tiers (C# parity).
def run_sim(traded, ticks, base, f1=0.35, f2=0.60, s_half=3, s_pause=4,
            rearm_green=2, probe_days=8):
    half = max(1, int(base / 2 + 0.5))   # AwayFromZero, same ladder as the sim / C#
    levels = [base, half, 1]
    equity = 0.0; peak = 0.0; streak = 0; green = 0; stuck = 0; ti = 0
    eq_path, sizes = [], []
    for i in range(len(ticks)):
        dd = peak - equity
        dd_ti = 0 if dd < f1 * CUSHION else (1 if dd < f2 * CUSHION else 2)
        streak_ti = 2 if streak >= s_pause else (1 if streak >= s_half else 0)
        target = max(dd_ti, streak_ti)
        if target > ti:
            ti = target; green = 0; stuck = 0
        elif target < ti and (green >= rearm_green or stuck >= probe_days):
            ti -= 1; green = 0; stuck = 0
        else:
            stuck += 1
        contracts = levels[ti]
        sizes.append(contracts)
        day_pnl = ticks[i] * contracts * TICK_USD if traded[i] else 0.0
        equity += day_pnl
        if equity > peak:
            peak = equity
        if traded[i]:
            if ticks[i] < 0:
                streak += 1; green = 0
            elif ticks[i] > 0:
                streak = 0; green += 1
        eq_path.append(equity)
    eq = np.array(eq_path)
    dd = (eq - np.maximum.accumulate(eq)).min()
    return eq, dd, np.array(sizes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=int, default=3)
    args = ap.parse_args()

    df = load_daily_ticks()
    traded = df["traded"].to_numpy()
    ticks = df["ticks"].to_numpy()
    n_trades = int(traded.sum())
    print(f"Secuencia: {df.date.min().date()} -> {df.date.max().date()} | "
          f"días={len(df)} | trades={n_trades} | cojín=${CUSHION:.0f} | base={args.base}\n")

    eqC, ddC, szC, tierC = run_csharp(traded, ticks, args.base)
    eqS, ddS, szS = run_sim(traded, ticks, args.base)

    print(f"{'engine':24} {'net':>10} {'maxDD':>10} {'quema?':>8}")
    print(f"{'C# DESPLEGADO (int)':24} {eqC[-1]:>+10.0f} {ddC:>+10.0f} "
          f"{'QUEMA' if ddC<=-CUSHION else 'seguro':>8}")
    print(f"{'sim canonico (int)':24} {eqS[-1]:>+10.0f} {ddS:>+10.0f} "
          f"{'QUEMA' if ddS<=-CUSHION else 'seguro':>8}")

    # per-trade size divergence (only where a trade was actually taken)
    mask = traded
    diff = (szC[mask] != szS[mask])
    print(f"\nTrades donde C# != sim en contratos: {diff.sum()}/{mask.sum()}")
    vals, cnts = np.unique(tierC, return_counts=True)
    tmap = {0: "full", 1: "half", 2: "min"}
    print("Uso tiers C# (todos los días): " +
          " ".join(f"{tmap.get(v,v)}={c}" for v, c in zip(vals, cnts)))

    if diff.sum():
        idx = np.where(mask)[0][diff][:8]
        print("\nPrimeras divergencias (fecha: C# vs sim contratos, ticks):")
        for j in idx:
            print(f"  {df.date.iloc[j].date()}  C#={szC[j]:>4}  sim={szS[j]:>4}  "
                  f"ticks={ticks[j]:+.0f}")

    print("\nVEREDICTO:")
    if diff.sum() == 0 and abs(ddC - ddS) < 1 and abs(eqC[-1] - eqS[-1]) < 1:
        print("  IDENTICO — el port C# reproduce el sim canonico exactamente.")
        print(f"  net ${eqC[-1]:+.0f}  maxDD ${ddC:+.0f}  "
              f"({'QUEMA' if ddC<=-CUSHION else 'SEGURO'} vs cojin ${CUSHION:.0f}).")
    else:
        net_gap = abs(eqC[-1] - eqS[-1])
        same_survival = (ddC <= -CUSHION) == (ddS <= -CUSHION)
        print(f"  DIVERGE — net gap ${net_gap:.0f}, DD gap ${abs(ddC-ddS):.0f}, "
              f"mismo veredicto de quema: {same_survival}.")
        print("  Revisar: C# y sim deberian compartir el mismo ladder entero ahora.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
