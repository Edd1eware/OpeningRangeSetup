"""Supplemental: can the CVD signal be used causally as an EXIT rule?

Policy per trade (all 564 executed trades, no entry filter):
  - if Dynamic_Alarm_Triggered: exit at alarm (Open_PnL_Ticks_At_Alarm),
    or trail/breakeven variants exported by the exporter
  - else: keep actual result
Compares against actual baseline. Assumes alarm columns are causal
(exporter computes them at alarm time, flagged causalAlarmCandidate).
"""
import csv
import json
import math
import re
from pathlib import Path

import numpy as np

RUN_DIR = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\visual_tests\04_run_replay_score_trade_results_dst_2025_2026_runs\X10_R1")
OUT_DIR = Path(__file__).resolve().parent

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


def summarize(x):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return dict(n=0)
    gw = x[x > 0].sum()
    gl = -x[x < 0].sum()
    return dict(
        n=int(len(x)),
        wr=round(float((x > 0).mean() * 100), 2),
        pf=round(float(gw / gl), 3) if gl > 0 else "inf",
        exp=round(float(x.mean()), 3),
        profit=float(x.sum()),
    )


rows = []
for path in sorted(RUN_DIR.glob("score_trade_result_*_NY.csv")):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        row = next(csv.DictReader(fh), {})
    if (row.get("Side") or "").strip() and (row.get("Entry_price") or "").strip():
        row["_date"] = row.get("fecha") or re.search(r"(\d{4}-\d{2}-\d{2})", path.name).group(1)
        rows.append(row)

actual = np.array([result_ticks(r.get("result TP SL BE")) for r in rows])
alarm = np.array([(r.get("Dynamic_Alarm_Triggered") or "").upper() == "TRUE" for r in rows])
pnl_at_alarm = np.array([fnum(r.get("Open_PnL_Ticks_At_Alarm")) for r in rows])
year = np.array([int(r["_date"][:4]) for r in rows])

policies = {"baseline_actual": actual.copy()}

exit_alarm = actual.copy()
usable = alarm & ~np.isnan(pnl_at_alarm)
exit_alarm[usable] = pnl_at_alarm[usable]
policies["exit_at_alarm"] = exit_alarm

for col, name in [
    ("Result_Trail_10", "trail_10_after_alarm"),
    ("Result_Trail_15", "trail_15_after_alarm"),
    ("Result_Trail_20", "trail_20_after_alarm"),
    ("Result_Breakeven_At_Alarm", "breakeven_after_alarm"),
]:
    v = np.array([fnum(r.get(col)) for r in rows])
    p = actual.copy()
    m = alarm & ~np.isnan(v)
    p[m] = v[m]
    policies[name] = p

report = {
    "alarm_triggered_n": int(alarm.sum()),
    "of_total": len(rows),
    "policies_all_trades": {k: summarize(v) for k, v in policies.items()},
    "policies_by_year": {
        k: {int(y): summarize(v[year == y]) for y in sorted(set(year))}
        for k, v in policies.items()
    },
}

out = OUT_DIR / "audit_exit_policy.json"
out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(out)
