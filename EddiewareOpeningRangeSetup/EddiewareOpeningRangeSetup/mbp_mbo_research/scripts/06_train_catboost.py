"""Walk-forward CatBoost filter on OR breakout events, reported year x metric.

Protocol
--------
* One model per test year: train on every session strictly BEFORE that year,
  test on that year. No shuffling, no k-fold: the data is a time series.
* A 5-session purge gap sits between train and test so nothing leaks.
* The baseline (take every breakout) is reported next to the filtered result;
  a filter that does not beat its own baseline OOS is noise.
* WR is always compared against the bracket's breakeven WR = SL/(TP+SL).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA, LOGS

EVENTS = DATA / "events" / "or_events.parquet"
FEATURES = DATA / "features" / "l2_features.parquet"
PURGE_DAYS = 5
COMMISSION_TICKS = 0.8      # ~$4 round turn on NQ at $5/tick
SLIPPAGE_TICKS = 1.0        # 1 tick of adverse fill, entry + exit combined
COST_TICKS = COMMISSION_TICKS + SLIPPAGE_TICKS

DROP = {"session", "signal_ts", "signal_ts_ny", "entry_ts", "exit_ts", "exit_kind",
        "ticks", "r_multiple", "exit_px", "entry_px", "year", "label",
        "or_high", "or_low", "mid"}


def report(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Year x metric table, per the project's backtest reporting standard."""
    rows = []
    for year, g in list(df.groupby("year")) + [("TOTAL", df)]:
        if g.empty:
            continue
        wins = g.ticks > 0
        gross_win = g.loc[wins, "ticks"].sum()
        gross_loss = -g.loc[~wins, "ticks"].sum()
        months = max(g.session.nunique() / 21, 1e-9)
        rows.append({
            "year": year,
            "trades": len(g),
            "trades/mes": round(len(g) / months, 1),
            "WR %": round(100 * wins.mean(), 1),
            "BE WR %": round(100 * g.breakeven_wr.mean(), 1),
            "R:R": round(g.rr.mean(), 2),
            "PF": round(gross_win / gross_loss, 2) if gross_loss else np.inf,
            "EV bruto": round(g.ticks.mean(), 2),
            f"EV neto (-{COST_TICKS}t)": round(g.ticks.mean() - COST_TICKS, 2),
        })
    out = pd.DataFrame(rows)
    print(f"\n=== {label} ===")
    print(out.to_string(index=False))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--or-minutes", type=int, default=15)
    ap.add_argument("--tp", type=int, default=40)
    ap.add_argument("--sl", type=int, default=20)
    ap.add_argument("--threshold", type=float, default=0.55)
    a = ap.parse_args()

    for p in (EVENTS, FEATURES):
        if not p.exists():
            print(f"missing {p}; run the earlier stages first.")
            return 1

    ev = pd.read_parquet(EVENTS)
    ev = ev[(ev.or_minutes == a.or_minutes) & (ev.tp_ticks == a.tp)
            & (ev.sl_ticks == a.sl)].copy()
    feats = pd.read_parquet(FEATURES)
    df = ev.merge(feats, on=["session", "or_minutes"], how="left")
    df["label"] = (df.ticks > 0).astype(int)
    df = df.sort_values("signal_ts").reset_index(drop=True)
    print(f"bracket TP{a.tp}/SL{a.sl} OR{a.or_minutes}m -> {len(df)} events, "
          f"{df.year.min()}-{df.year.max()}")

    x_cols = [c for c in df.columns
              if c not in DROP and pd.api.types.is_numeric_dtype(df[c])]
    print(f"{len(x_cols)} features")

    base = report(df, "BASELINE - take every breakout")

    picks = []
    years = sorted(df.year.unique())
    for test_year in years[1:]:                  # first year has no history
        tr = df[df.year < test_year]
        te = df[df.year == test_year]
        if len(tr) < 100 or te.empty:
            continue
        cutoff = pd.Timestamp(te.signal_ts.min()) - pd.Timedelta(days=PURGE_DAYS)
        tr = tr[pd.to_datetime(tr.signal_ts) < cutoff]

        model = CatBoostClassifier(
            iterations=400, depth=4, learning_rate=0.03,
            l2_leaf_reg=6, loss_function="Logloss", random_seed=7,
            verbose=False, allow_writing_files=False)
        model.fit(tr[x_cols].fillna(-999), tr.label)

        te = te.copy()
        te["p"] = model.predict_proba(te[x_cols].fillna(-999))[:, 1]
        picks.append(te[te.p >= a.threshold])

        imp = pd.Series(model.get_feature_importance(), index=x_cols)
        print(f"  {test_year}: train={len(tr)} test={len(te)} "
              f"kept={len(picks[-1])} top={', '.join(imp.nlargest(3).index)}")

    if not picks:
        print("not enough history for a walk-forward.")
        return 1
    oos = pd.concat(picks, ignore_index=True)
    filt = report(oos, f"CATBOOST FILTER OOS (p >= {a.threshold})")

    LOGS.mkdir(parents=True, exist_ok=True)
    base.to_csv(LOGS / "report_baseline.csv", index=False)
    filt.to_csv(LOGS / "report_catboost_oos.csv", index=False)
    print(f"\nreports -> {LOGS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
