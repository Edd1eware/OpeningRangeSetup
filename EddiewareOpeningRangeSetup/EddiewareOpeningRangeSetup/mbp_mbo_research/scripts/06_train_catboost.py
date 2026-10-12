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

# Columns that must never reach the model.
# Outcomes: knowing any of these is knowing the answer. `mins_to_exit` is the
# worst of them because it is numeric and looks like a feature.
# Absolute prices: they encode the date, so the model learns the calendar
# instead of the setup.
# Constants after filtering by bracket: no information, just noise in the splits.
DROP = {
    # outcomes
    "ticks", "r_multiple", "exit_kind", "exit_ts", "exit_px", "mins_to_exit",
    "label", "filled",
    # identifiers and timestamps
    "session", "signal_ts", "signal_ts_ny", "signal_minute_ny", "entry_ts", "year",
    # absolute price levels
    "entry_px", "or_high", "or_low", "vwap", "mid",
    # known only at or after the fill
    "fill_wait_s",
    # constant once a bracket is selected
    "tp_ticks", "sl_ticks", "rr", "breakeven_wr",
}


MIN_N_YEAR = 30     # below this a yearly row is noise, not evidence


def report(df: pd.DataFrame, label: str, universe: pd.DataFrame | None = None
           ) -> pd.DataFrame:
    """Year x metric table, per the project's backtest reporting standard.

    `universe` is the unfiltered event set: trades/mes is measured against the
    calendar months actually available, so a selective filter correctly shows a
    LOWER trade frequency instead of being rescaled back up.
    """
    rows = []
    univ = df if universe is None else universe
    for year, g in list(df.groupby("year")) + [("TOTAL", df)]:
        if g.empty:
            continue
        pool = univ if year == "TOTAL" else univ[univ.year == year]
        months = max(pd.to_datetime(pool.session).dt.to_period("M").nunique(), 1)
        wins = g.ticks > 0
        gross_win = g.loc[wins, "ticks"].sum()
        gross_loss = -g.loc[~wins, "ticks"].sum()
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
            "n ok": "" if len(g) >= MIN_N_YEAR else f"<{MIN_N_YEAR}!",
        })
    out = pd.DataFrame(rows)
    print(f"\n=== {label} ===")
    print(out.to_string(index=False))
    thin = out[(out.year != "TOTAL") & (out["n ok"] != "")]
    if not thin.empty:
        print(f"  WARNING: {len(thin)} year(s) under {MIN_N_YEAR} trades "
              "-> those rows carry no statistical weight.")
    return out


def placebo(universe: pd.DataFrame, picked: pd.DataFrame, iters: int = 2000,
            seed: int = 17) -> float:
    """p-value of the filter vs. picking the same count of trades at random.

    The null is 'the filter selects no better than a coin'. Drawing the same
    number of trades per year from the same pool is the only honest null: a
    small, lucky subset of a zero-edge pool shows a great PF all by itself.
    """
    rng = np.random.default_rng(seed)
    target = picked.ticks.mean()
    counts = picked.groupby("year").size().to_dict()
    pools = {y: universe.loc[universe.year == y, "ticks"].to_numpy()
             for y in counts}
    better = 0
    for _ in range(iters):
        draws = [rng.choice(pools[y], size=min(k, len(pools[y])), replace=False)
                 for y, k in counts.items() if len(pools[y])]
        if draws and np.concatenate(draws).mean() >= target:
            better += 1
    return better / iters


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bracket", type=int, default=40,
                    help="bracket size in ticks; TP = SL (1:1)")
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--entry-mode", default="market",
                    help="which entry mode to train on; the modes are not "
                         "comparable rows and must not be pooled")
    a = ap.parse_args()
    a.tp = a.sl = a.bracket

    for p in (EVENTS, FEATURES):
        if not p.exists():
            print(f"missing {p}; run the earlier stages first.")
            return 1

    ev = pd.read_parquet(EVENTS)
    ev = ev[(ev.tp_ticks == a.tp) & (ev.sl_ticks == a.sl)
            & (ev.entry_mode == a.entry_mode) & ev.filled].copy()
    feats = pd.read_parquet(FEATURES)
    on = ["session"] + (["or_minutes"] if "or_minutes" in feats.columns
                        and "or_minutes" in ev.columns else [])
    df = ev.merge(feats, on=on, how="left")
    df["label"] = (df.ticks > 0).astype(int)
    df = df.sort_values("signal_ts").reset_index(drop=True)
    print(f"bracket 1:1 {a.bracket} ticks, entrada {a.entry_mode} -> "
          f"{len(df)} events, {df.year.min()}-{df.year.max()}")

    x_cols = [c for c in df.columns
              if c not in DROP and pd.api.types.is_numeric_dtype(df[c])]
    print(f"{len(x_cols)} features")

    base = report(df, "BASELINE - take every qualifying setup")

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
    tested = df[df.year.isin(oos.year.unique())]
    filt = report(oos, f"CATBOOST FILTER OOS (p >= {a.threshold})", universe=tested)

    p_val = placebo(tested, oos)
    kept = 100 * len(oos) / max(len(tested), 1)
    print(f"\nselectivity: kept {len(oos)}/{len(tested)} OOS events ({kept:.1f}%)")
    print(f"placebo p-value (same count drawn at random): {p_val:.3f}")
    if p_val > 0.05:
        print("  -> NOT significant. The filter does not beat a random pick of "
              "the same size. Treat the pretty PF above as noise.")
    elif len(oos) < MIN_N_YEAR:
        print(f"  -> significant but n={len(oos)} is tiny; re-check with more data.")
    else:
        print("  -> survives the placebo. Still needs a forward test before size.")

    rep = DATA / "reports"
    rep.mkdir(parents=True, exist_ok=True)
    base.to_csv(rep / f"report_baseline_{a.bracket}t.csv", index=False)
    filt.to_csv(rep / f"report_catboost_oos_{a.bracket}t.csv", index=False)
    print(f"\nreports -> {rep}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
