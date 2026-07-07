"""Kill-switch backtester on the REAL trade sequence (2025-2026).

Goal (design brief PROGRESO_05 §2b): a robust, deterministic size-throttle that
adapts to the OBSERVED losing streaks (slow red months + short SL clusters), keeps
the drawdown under the Lucid $4,500 cushion, and does NOT cut the good months.

Design (deterministic, no ML):
  State per EOD:
    peak      = max equity so far
    dd        = peak - equity            (drawdown from peak, $)
    streak    = consecutive losing days
    tier      = current size multiplier (hysteresis on the way up)
  Size decision (graduated, cushion-anchored):
    dd < f1*cushion            -> FULL   (base contracts)
    f1 <= dd < f2*cushion      -> HALF
    dd >= f2*cushion           -> PAUSE  (0 contracts, sit out)
    streak override: streak>=s_half -> at most HALF; streak>=s_pause -> PAUSE
  Re-arm: step UP one tier only after `rearm_green` green days (anti-whipsaw).

The throttle makes each loss near the floor smaller, so the floor is mathematically
harder to hit; it also sits out the deep-bleed stretches.

Usage:
    python -u kill_switch_sim.py                 # default config, vs fixed 6c and 3c
    python -u kill_switch_sim.py --sweep          # grid-search thresholds
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


def run_fixed(ticks, dates, contracts):
    """Fixed size baseline. Returns equity path + stats."""
    eq = np.cumsum(ticks * contracts * TICK_USD)
    dd = (eq - np.maximum.accumulate(eq)).min()
    return eq, dd


TIER_LEVELS = [1.0, 0.5, 0.25]   # full, half, min (never 0 -> stays in the game)


def run_killswitch(traded, ticks, dates, base, f1, f2, s_half, s_pause,
                   rearm_green, probe_days=8):
    """Graduated throttle, min-tier floor (never full pause), re-arm on green days
    OR after `probe_days` stuck (anti-deadlock). Returns equity, max_dd, tiers, low_days, taken."""
    equity = 0.0
    peak = 0.0
    streak = 0            # consecutive losing days
    green = 0             # consecutive green days (for re-arm)
    stuck = 0             # days stuck at current low tier (time-based probe)
    ti = 0                # tier index into TIER_LEVELS (0=full)
    eq_path, tiers = [], []
    low_days = 0
    taken = 0
    for i in range(len(ticks)):
        dd = peak - equity
        # target tier index from dd (0 full, 1 half, 2 min)
        dd_ti = 0 if dd < f1 * CUSHION else (1 if dd < f2 * CUSHION else 2)
        streak_ti = 0
        if streak >= s_pause:
            streak_ti = 2
        elif streak >= s_half:
            streak_ti = 1
        target = max(dd_ti, streak_ti)     # deeper tier index = smaller size

        if target > ti:            # cut instantly
            ti = target; green = 0; stuck = 0
        elif target < ti and (green >= rearm_green or stuck >= probe_days):
            ti -= 1                 # step up ONE level (green re-arm OR time probe)
            green = 0; stuck = 0
        else:
            stuck += 1

        contracts = base * TIER_LEVELS[ti]
        if ti > 0:
            low_days += 1
        if traded[i]:
            day_pnl = ticks[i] * contracts * TICK_USD
            taken += 1
        else:
            day_pnl = 0.0

        equity += day_pnl
        if equity > peak:
            peak = equity
        if traded[i]:
            if ticks[i] < 0:
                streak += 1; green = 0
            elif ticks[i] > 0:
                streak = 0; green += 1
        eq_path.append(equity)
        tiers.append(TIER_LEVELS[ti])

    eq = np.array(eq_path)
    dd = (eq - np.maximum.accumulate(eq)).min()
    return eq, dd, np.array(tiers), low_days, taken


def summarize(name, eq, dd, extra=""):
    burned = dd <= -CUSHION
    flag = "[QUEMA]" if burned else "[seguro]"
    print(f"{name:28} net=${eq[-1]:>+8.0f}  maxDD=${dd:>+7.0f}  {flag}  {extra}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=int, default=6)
    ap.add_argument("--f1", type=float, default=0.35)
    ap.add_argument("--f2", type=float, default=0.60)
    ap.add_argument("--s-half", type=int, default=3)
    ap.add_argument("--s-pause", type=int, default=4)
    ap.add_argument("--rearm-green", type=int, default=2)
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()

    df = load_daily_ticks()
    traded = df["traded"].to_numpy()
    ticks = df["ticks"].to_numpy()
    dates = df["date"].to_numpy()
    print(f"Secuencia: {df.date.min().date()} -> {df.date.max().date()} | "
          f"días={len(df)} | trades={int(traded.sum())} | cojín=${CUSHION:.0f}\n")

    # baselines
    for c in (6, 3):
        eq, dd = run_fixed(ticks, dates, c)
        summarize(f"FIJO {c}c", eq, dd)
    print()

    if args.sweep:
        print("=== SWEEP (base, f1, f2, s_half, s_pause) ===")
        best = None
        for base in (4, 5, 6, 7, 8):
            for f1 in (0.30, 0.35, 0.40):
                for f2 in (0.55, 0.60, 0.70):
                    eq, dd, tiers, low_days, taken = run_killswitch(
                        traded, ticks, dates, base, f1, f2,
                        args.s_half, args.s_pause, args.rearm_green)
                    if dd > -CUSHION:  # survives
                        score = eq[-1]
                        if best is None or score > best[0]:
                            best = (score, base, f1, f2, dd, low_days, taken)
        if best:
            s, base, f1, f2, dd, low_days, taken = best
            print(f"MEJOR seguro: base={base}c f1={f1} f2={f2} -> "
                  f"net=${s:+.0f} maxDD=${dd:+.0f} low_days={low_days} taken={taken}")
            print(f"  (comparar vs FIJO 3c = +$22,410 seguro)")
        else:
            print("Ningún config sobrevive el cojín en el sweep (revisar rangos).")
        return 0

    # single config
    eq, dd, tiers, low_days, taken = run_killswitch(
        traded, ticks, dates, args.base, args.f1, args.f2,
        args.s_half, args.s_pause, args.rearm_green)
    summarize(f"KILL-SWITCH base={args.base}c", eq, dd,
              extra=f"low_days={low_days} taken={taken}")
    # tier usage
    vals, cnts = np.unique(tiers, return_counts=True)
    tmap = {1.0: "full", 0.5: "half", 0.25: "min"}
    usage = " ".join(f"{tmap.get(v,v)}={c}" for v, c in zip(vals, cnts))
    print(f"\nUso de tiers (días): {usage}")
    # monthly with kill-switch
    df["eq"] = eq
    df["dmonth"] = df["date"].dt.to_period("M")
    df["pnl"] = df["eq"].diff().fillna(df["eq"])
    m = df.groupby("dmonth")["pnl"].sum()
    print("\n=== NET mensual con kill-switch (base {}c) ===".format(args.base))
    for ym, v in m.items():
        print(f"{str(ym)}  ${v:>+8.0f}")
    print(f"\nComparación clave:")
    eq6, dd6 = run_fixed(ticks, dates, 6)
    eq3, dd3 = run_fixed(ticks, dates, 3)
    print(f"  FIJO 6c   : net=${eq6[-1]:+.0f}  DD=${dd6:+.0f}  (QUEMA)")
    print(f"  FIJO 3c   : net=${eq3[-1]:+.0f}  DD=${dd3:+.0f}  (seguro)")
    print(f"  KILL {args.base}c : net=${eq[-1]:+.0f}  DD=${dd:+.0f}  "
          f"({'seguro' if dd>-CUSHION else 'QUEMA'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
