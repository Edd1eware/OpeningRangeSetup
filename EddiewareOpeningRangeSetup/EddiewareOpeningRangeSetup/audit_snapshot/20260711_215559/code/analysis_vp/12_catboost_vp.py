"""CatBoost vetting of the Volume-Profile features: do they help identify the
best +60t signals, and does it survive a FRESH holdout?

Split by season/year (temporal, never random):
    train  = earliest years
    holdout= last year(s)  (fresh, never seen in fit)
Reports:
  - AUC train vs holdout (overfit gap)
  - feature importance ranking (which profiles matter: ON? PD VA? PREOPEN?)
  - top-20% lift: WR of the model's top-quantile vs base rate, PER YEAR
A feature set "helps" ONLY if the top-quantile WR beats base rate on the FRESH
holdout, stable year-over-year. In-sample-only lift = dead (like candle/efficiency).

This is feature VETTING, not a full EV backtest. If VP survives here, feed the
survivors into the existing OR-CB bracket backtest for WR/PF/EV per year.

Usage:
    python -u 12_catboost_vp.py
    python -u 12_catboost_vp.py --data merged_slide.parquet --holdout-year 2026 --fade
    python -u 12_catboost_vp.py --use-survivors   # only vp_survivors.txt features
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import roc_auc_score


def build_label(df: pd.DataFrame, fade: bool) -> pd.Series:
    up = df["break_dir"].astype(str).str.lower().eq("up")
    if fade:
        y = (up & df["hit60_dn"].astype(bool)) | (~up & df["hit60_up"].astype(bool))
    else:
        y = (up & df["hit60_up"].astype(bool)) | (~up & df["hit60_dn"].astype(bool))
    return y.astype(int)


def vp_feature_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns
            if c.startswith(("distance_to_PD", "distance_to_ON", "distance_to_PREOPEN",
                             "position_vs_"))
            or c == "profile_confluence_count"]


def top_quantile_wr(y: np.ndarray, p: np.ndarray, q: float = 0.80):
    """WR (mean y) among the top (1-q) fraction by predicted proba, + n."""
    if len(y) == 0:
        return np.nan, 0
    thr = np.quantile(p, q)
    m = p >= thr
    if m.sum() == 0:
        return np.nan, 0
    return float(y[m].mean()), int(m.sum())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="merged_slide.parquet")
    ap.add_argument("--holdout-year", type=int, default=None,
                    help="year used as fresh holdout (default = max year)")
    ap.add_argument("--fade", action="store_true")
    ap.add_argument("--use-survivors", action="store_true",
                    help="restrict to features listed in vp_survivors.txt")
    ap.add_argument("--top-q", type=float, default=0.80, help="top-(1-q) quantile for lift")
    args = ap.parse_args()

    df = pd.read_parquet(args.data)
    df["y"] = build_label(df, args.fade)

    feats = vp_feature_cols(df)
    if args.use_survivors and os.path.exists("vp_survivors.txt"):
        keep = [l.strip() for l in open("vp_survivors.txt") if l.strip()]
        feats = [c for c in feats if c in keep]
        print(f"Usando {len(feats)} features sobrevivientes de vp_survivors.txt")
    if not feats:
        print("Sin features VP.", file=sys.stderr)
        return 1

    years = sorted(df["year"].dropna().unique().astype(int))
    holdout = args.holdout_year or max(years)
    train_df = df[df["year"] < holdout]
    hold_df = df[df["year"] == holdout]
    if train_df.empty or hold_df.empty:
        print(f"Split inválido: train años<{holdout}={len(train_df)}, "
              f"holdout {holdout}={len(hold_df)}", file=sys.stderr)
        return 1

    label = "FADE" if args.fade else "CONTINUATION"
    print(f"Label={label} | features={len(feats)} | "
          f"train años<{holdout} n={len(train_df):,} (base {train_df['y'].mean():.3f}) | "
          f"holdout {holdout} n={len(hold_df):,} (base {hold_df['y'].mean():.3f})")

    Xtr, ytr = train_df[feats].astype(float), train_df["y"].to_numpy()
    Xho, yho = hold_df[feats].astype(float), hold_df["y"].to_numpy()

    model = CatBoostClassifier(
        iterations=400, depth=4, learning_rate=0.05,
        l2_leaf_reg=6.0, loss_function="Logloss",
        random_seed=42, verbose=False,
    )
    model.fit(Pool(Xtr, ytr))

    ptr = model.predict_proba(Xtr)[:, 1]
    pho = model.predict_proba(Xho)[:, 1]
    auc_tr = roc_auc_score(ytr, ptr) if len(np.unique(ytr)) > 1 else np.nan
    auc_ho = roc_auc_score(yho, pho) if len(np.unique(yho)) > 1 else np.nan
    print(f"\nAUC train={auc_tr:.3f}  holdout={auc_ho:.3f}  gap={auc_tr-auc_ho:+.3f}")
    if auc_ho < 0.53:
        print("  -> holdout AUC ~ azar: VP NO discrimina fresh. (prior confirmado)")

    # importance
    imp = (pd.DataFrame({"feature": feats, "importance": model.get_feature_importance()})
           .sort_values("importance", ascending=False))
    print("\n=== Importancia (top 15) ===")
    print(imp.head(15).round(2).to_string(index=False))

    # top-quantile lift per year (out-of-fit rows only: holdout + a proper CV would be
    # better, but for vetting we show holdout per-year plus the whole-frame per year with
    # a note that pre-holdout years are IN-SAMPLE).
    print(f"\n=== Lift top-{int((1-args.top_q)*100)}% (WR del cuantil alto vs base) por año ===")
    print(f"{'year':>6} {'insample':>9} {'n':>6} {'base':>6} {'topWR':>7} {'n_top':>6} {'lift':>7}")
    pall = model.predict_proba(df[feats].astype(float))[:, 1]
    df = df.assign(_p=pall)
    for yr in years:
        sub = df[df["year"] == yr]
        base = sub["y"].mean()
        wr, ntop = top_quantile_wr(sub["y"].to_numpy(), sub["_p"].to_numpy(), args.top_q)
        insample = "IN" if yr < holdout else "FRESH"
        lift = (wr - base) if not np.isnan(wr) else np.nan
        print(f"{yr:>6} {insample:>9} {len(sub):>6} {base:>6.3f} "
              f"{wr:>7.3f} {ntop:>6} {lift:>+7.3f}")

    print("\nCriterio: la fila FRESH debe tener lift>0 estable. Si solo IN levanta -> muerto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
