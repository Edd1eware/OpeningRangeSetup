"""Time-to-pass a Lucid 150k eval using the HONEST walk-forward OOS trades.

Rebuilds the at-entry-only walk-forward (same as audit_calc.py), collects the
per-trade OOS results (2023-2026, 284 trades), then Monte Carlo:
  - pass: equity >= +9000 USD
  - bust: trailing drawdown (peak - equity) >= 4500 USD
  - no time limit; capped at MAX_TRADES to detect "never"
Scenarios: contracts 1..4, net (slippage 1.95 + commission 1.0 ticks) and gross.
"""
import csv
import json
import math
import re
from pathlib import Path

import numpy as np

# Original X10_R1 was reset by ongoing replay runs; use the frozen, hash-verified
# Fase 0 snapshot copy instead (identical 730 files).
RUN_DIR = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup\audit_snapshot\20260711_215559\data\X10_R1")
OUT_DIR = Path(__file__).resolve().parent

TICK_VALUE = 5.0
COST_TICKS = 2.95  # measured slippage 1.95 + NQ commission ~1 tick
TARGET = 9000.0
DD_LIMIT = 4500.0
SIMS = 10000
MAX_TRADES = 3000
SEED = 20260712

NAN_TOKENS = {"", "OPEN", "TIME_OVER", "NO_TRADE", "HOLYDAY NO DATA"}


def fnum(v, default=np.nan):
    text = str(v or "").strip()
    if not text or text.upper() in NAN_TOKENS:
        return default
    try:
        return float(text.replace("+", ""))
    except ValueError:
        return default


def result_ticks(v):
    text = str(v or "").strip().upper()
    if text == "BE":
        return 0.0
    if text in NAN_TOKENS:
        return 0.0
    return fnum(text, 0.0)


def sim_tp_sl(actual, mfe, mae, tp, sl):
    res = np.clip(actual, -sl, tp)
    both = (mfe >= tp) & (mae >= sl)
    hit_tp = (mfe >= tp) & ~both
    hit_sl = (mae >= sl) | both
    res = res.copy()
    res[hit_tp] = tp
    res[hit_sl] = -sl
    return res


trades = []
for path in sorted(RUN_DIR.glob("score_trade_result_*_NY.csv")):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        row = next(csv.DictReader(fh), {})
    if (row.get("Side") or "").strip() and (row.get("Entry_price") or "").strip():
        row["_date"] = row.get("fecha") or re.search(r"(\d{4}-\d{2}-\d{2})", path.name).group(1)
        trades.append(row)

actual = np.array([result_ticks(r.get("result TP SL BE")) for r in trades])
mfe = np.array([fnum(r.get("MFE_ticks")) for r in trades])
mae = np.array([fnum(r.get("MAE_ticks")) for r in trades])
year = np.array([int(r["_date"][:4]) for r in trades])
month = np.array([r["_date"][:7] for r in trades])
score = np.array([fnum(r.get("score total")) for r in trades])
side = np.array([(r.get("Side") or "").strip() for r in trades])
speed = np.array([(r.get("Speed_Profile") or "Unknown").strip() for r in trades])

bool_cols = [
    "Range_OK", "Body_OK", "Volume_OK", "Delta_OK", "VWAP_OK", "Speed_OK",
    "Volume_Increasing", "Delta_With_Side", "Price_Accepted_After_Imbalance",
    "Price_Rejected_After_Imbalance", "APlus_Structure", "APlus_Absorption",
    "APlus_Speed",
]
bools = {c: np.array([(r.get(c) or "").upper() == "TRUE" for r in trades]) for c in bool_cols}


def entry_filters():
    out = [("ALL", np.ones(len(trades), dtype=bool))]
    for s in sorted(set(side)):
        out.append((f"side={s}", side == s))
    for s in sorted(set(speed)):
        out.append((f"speed={s}", speed == s))
    for th in [6, 7, 8, 9]:
        out.append((f"score>={th}", score >= th))
    for c, arr in bools.items():
        out.append((f"{c}=TRUE", arr))
        out.append((f"{c}=FALSE", ~arr))
    return out


# rebuild walk-forward OOS trade series (identical selection to audit_calc.py)
oos_ticks = []
oos_months = set()
for ey in [2023, 2024, 2025, 2026]:
    train_mask = year < ey
    best = (None, -1e18, None, None)
    for name, fm in entry_filters():
        tm = fm & train_mask
        if tm.sum() < 60:
            continue
        for tp in (60, 80, 100, 120):
            for sl in (30, 40, 50):
                s = sim_tp_sl(actual, mfe, mae, tp, sl)
                x = s[tm]
                metric = x.mean() * math.sqrt(len(x))
                if metric > best[1]:
                    best = (name, metric, tp, sl)
    name, _, tp, sl = best
    chosen = dict(entry_filters())[name]
    s = sim_tp_sl(actual, mfe, mae, tp, sl)
    m = chosen & (year == ey)
    oos_ticks.extend(s[m].tolist())
    oos_months.update(month[m].tolist())

oos_ticks = np.array(oos_ticks)
trades_per_month = len(oos_ticks) / len(oos_months)


def lucid_mc(pnl_usd, rng):
    """Returns (status, trades_used). status: 1 pass, -1 bust, 0 never."""
    eq = peak = 0.0
    n = 0
    while n < MAX_TRADES:
        take = rng.integers(0, len(pnl_usd))
        block = pnl_usd[take:take + 8]
        for pnl in block:
            n += 1
            eq += pnl
            peak = max(peak, eq)
            if peak - eq >= DD_LIMIT:
                return -1, n
            if eq >= TARGET:
                return 1, n
            if n >= MAX_TRADES:
                break
    return 0, n


scenarios = {}
for label, cost in [("net", COST_TICKS), ("gross_no_costs", 0.0)]:
    ticks = oos_ticks - cost
    for c in (1, 2, 3, 4):
        pnl_usd = ticks * TICK_VALUE * c
        rng = np.random.default_rng(SEED + c)
        res = [lucid_mc(pnl_usd, rng) for _ in range(SIMS)]
        status = np.array([r[0] for r in res])
        n_used = np.array([r[1] for r in res])
        pass_n = n_used[status == 1]
        scenarios[f"{label}_{c}c"] = {
            "ev_usd_per_trade": round(float(pnl_usd.mean()), 2),
            "pass_pct": round(float((status == 1).mean() * 100), 1),
            "bust_pct": round(float((status == -1).mean() * 100), 1),
            "never_3000_trades_pct": round(float((status == 0).mean() * 100), 1),
            "median_trades_to_pass": float(np.median(pass_n)) if len(pass_n) else None,
            "median_months_to_pass": round(float(np.median(pass_n)) / trades_per_month, 1) if len(pass_n) else None,
            "p90_months_to_pass": round(float(np.percentile(pass_n, 90)) / trades_per_month, 1) if len(pass_n) else None,
        }

report = {
    "oos_trades": len(oos_ticks),
    "oos_active_months": len(oos_months),
    "trades_per_month": round(trades_per_month, 2),
    "oos_exp_gross_ticks": round(float(oos_ticks.mean()), 2),
    "oos_exp_net_ticks": round(float((oos_ticks - COST_TICKS).mean()), 2),
    "oos_std_ticks": round(float(oos_ticks.std(ddof=1)), 2),
    "lucid": {"target_usd": TARGET, "trailing_dd_usd": DD_LIMIT, "sims": SIMS, "max_trades": MAX_TRADES},
    "scenarios": scenarios,
}

out = OUT_DIR / "audit_lucid_time.json"
out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(report, indent=2, ensure_ascii=False))
