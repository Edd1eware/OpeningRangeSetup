"""Integration check: does the LIVE C# kill-switch (Execution Manager strategy) size
each trade exactly as the validated model predicts?

Reads the strategy's own trade log `strategy_tester_trades.csv` (written by
02_C_ATASExecutionManagerStrategy: fecha,side,contratos,entry_fill,exit_fill,ticks,
pnl_usd,exit_motivo[,challenge_equity,...]) and re-runs the SAME kill-switch model
(12_KillSwitchSizer / kill_switch_sim.py, integer tiers, streak-before order) fed the
ACTUAL realized pnl_usd sequence. It then compares, per trade:

  predicted contracts (model CurrentSize BEFORE the trade)  vs  actual `contratos`

If they match on every trade, the C# port reproduces the design in the live strategy
(persistence + OnTradeClosed timing are correct). Any mismatch localizes an integration
bug. Also cross-checks the model balance against the `challenge_equity` column if present.

This is the REAL integration validation (vs kill_switch_parity.py which models sizing
from the exporter's canonical tick sequence). Run AFTER `06_run_strategy_replay.py`:
    python -u kill_switch_integration_check.py --base 3
    python -u kill_switch_integration_check.py --base 3 --csv <path a strategy_tester_trades.csv>
"""
from __future__ import annotations

import argparse
import csv
import os

CUSHION = 4500.0
DEFAULT_CSV = (r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
               r"\visual_tests\strategy_tester_results\strategy_tester_trades.csv")


def load_trades(path):
    """Return list of dicts in FILE order (= strategy execution order in replay)."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        try:
            out.append({
                "fecha": r.get("fecha", ""),
                "side": r.get("side", ""),
                "contratos": int(float(r["contratos"])),
                "ticks": float(r["ticks"]),
                "pnl_usd": float(r["pnl_usd"]),
                # optional live equity snapshot (present in the richer header)
                "challenge_equity": (float(r["challenge_equity"])
                                     if r.get("challenge_equity") not in (None, "", "nan")
                                     else None),
            })
        except (KeyError, ValueError):
            # skip malformed / header-less rows
            continue
    return out


def model_predict(trades, base, f1=0.35, f2=0.60, s_half=3, s_pause=4,
                  rearm_green=2, probe_days=8):
    """Replicate 12_KillSwitchSizer fed the ACTUAL realized pnl_usd sequence.
    Returns per-trade (predicted_contracts, model_balance_after). Integer tiers,
    streak/green updated BEFORE the tier decision (the deployed/corrected order)."""
    half = max(1, int(base / 2 + 0.5))     # AwayFromZero, matches C# Math.Round
    levels = [base, half, 1]

    tier = streak = green = stuck = 0
    balance = peak = 0.0
    preds = []
    for t in trades:
        pred = levels[tier]                 # CurrentSize BEFORE this entry
        # --- OnTradeClosed(pnl_usd) with the REAL realized pnl ---
        pnl = t["pnl_usd"]
        balance += pnl
        if balance > peak:
            peak = balance
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
        preds.append((pred, balance, tier))
    return preds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=int, default=3)
    ap.add_argument("--csv", default=DEFAULT_CSV)
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        print(f"NO EXISTE el trade-log de la strategy:\n  {args.csv}\n"
              "Corre primero: python -u 06_run_strategy_replay.py --all")
        return 2

    trades = load_trades(args.csv)
    if not trades:
        print(f"Trade-log vacío o sin filas válidas: {args.csv}")
        return 2

    print(f"Trade-log: {args.csv}")
    print(f"Trades: {len(trades)} | base={args.base} | cojín=${CUSHION:.0f}\n")

    preds = model_predict(trades, args.base)

    mismatches = []
    eq_mismatches = []
    tier_counts = {0: 0, 1: 0, 2: 0}
    net = 0.0
    for i, (t, (pred, bal, tier_after)) in enumerate(zip(trades, preds)):
        actual = t["contratos"]
        net += t["pnl_usd"]
        # tier that PRODUCED this trade's size (reverse-map pred to index)
        half = max(1, int(args.base / 2 + 0.5))
        used_tier = 0 if pred == args.base else (1 if pred == half else 2)
        tier_counts[used_tier] += 1
        if pred != actual:
            mismatches.append((i, t["fecha"], pred, actual, t["pnl_usd"]))
        if t["challenge_equity"] is not None and abs(t["challenge_equity"] - bal) > 0.5:
            eq_mismatches.append((t["fecha"], bal, t["challenge_equity"]))

    max_dd = 0.0
    peak = 0.0
    run = 0.0
    for t in trades:
        run += t["pnl_usd"]
        if run > peak:
            peak = run
        max_dd = min(max_dd, run - peak)

    print(f"Uso de tiers (por trade tomado): full={tier_counts[0]} "
          f"half={tier_counts[1]} min={tier_counts[2]}")
    print(f"Net real: ${net:+,.0f} | MaxDD real: ${max_dd:+,.0f} "
          f"({'QUEMA' if max_dd <= -CUSHION else 'seguro'} vs ${CUSHION:.0f})\n")

    print("VEREDICTO INTEGRACIÓN:")
    if not mismatches:
        print(f"  ✅ MATCH — los {len(trades)} trades usan EXACTAMENTE los contratos que")
        print("     predice el modelo del kill-switch. Persistencia + timing OK.")
    else:
        print(f"  ❌ {len(mismatches)}/{len(trades)} trades con contratos != modelo:")
        print("     idx | fecha | modelo | real | pnl_usd")
        for i, fecha, pred, actual, pnl in mismatches[:15]:
            print(f"     {i:>4} | {fecha} | {pred:>6} | {actual:>4} | {pnl:+.0f}")
        print("     Causa probable: timing OnTradeClosed vs entry, killswitch_state.txt")
        print("     no persistido/leído, o rounding de tier distinto.")

    if eq_mismatches:
        print(f"\n  ⚠️ challenge_equity difiere del balance del modelo en "
              f"{len(eq_mismatches)} trades (feed de equity sospechoso):")
        for fecha, bal, eq in eq_mismatches[:8]:
            print(f"     {fecha}: modelo ${bal:+.0f} vs log ${eq:+.0f}")

    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
