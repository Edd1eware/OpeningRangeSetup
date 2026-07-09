#!/usr/bin/env python3
"""CatBoost descubrimiento LVN (2026-07-09) — dev DST 2025, holdout DST 2026.

Doctrina: CatBoost = herramienta de descubrimiento, no de ordeñe. Modelo chico (n~400),
features causales al momento del retest, target = win del bracket 80/80. El holdout 2026 se
toca UNA vez. Nada se optimiza mirando 2026.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool

FILES = [
    "outputs/lvn_or_strategy_replay/lvn_retest_DST_2025_csv/LVN_Events.csv",
    "outputs/lvn_or_strategy_replay/lvn_retest_DST_2026_full_v2_csv/LVN_Events.csv",
]
TARGET_COLUMN = "tp_sl_80_80_result"
NUMERIC_FEATURES = [
    "distance_to_context_vah_ticks", "distance_to_context_poc_ticks", "distance_to_context_val_ticks",
    "distance_to_minute_poc_ticks", "distance_to_vwap_ticks", "distance_to_open_ticks",
    "lvn_volume", "lvn_depth", "lvn_width_ticks",
    "delta_touch_bar", "delta_change_touch_bar", "lvn_retest_delta",
    "aggression_volume_per_second", "aggression_delta_per_second", "tape_speed_trades_per_second",
    "approach_speed_ticks_per_second", "distance_traveled_to_lvn_ticks", "deceleration_ratio",
    "seconds_from_0931", "seconds_touch_to_entry", "retest_number", "prior_move_from_open_ticks",
    "context_prob_D", "context_prob_P", "context_prob_b", "context_prob_trend_up",
    "context_prob_trend_down", "context_shape_confidence", "minute_shape_confidence",
    "vwap_slope_ticks", "ema_slope_ticks",
]
CATEGORICAL_FEATURES = ["lvn_interaction", "approach", "prior_movement_direction", "context_profile_shape"]


def main() -> int:
    events = pd.concat([pd.read_csv(path) for path in FILES], ignore_index=True)
    events = events.drop_duplicates(subset=["event_id"], keep="last").copy()
    events["year"] = pd.to_datetime(events["date"]).dt.year
    events["month"] = pd.to_datetime(events["date"]).dt.to_period("M")
    resolved = events.loc[events[TARGET_COLUMN].isin(["TP", "SL"])].copy()
    resolved["win"] = (resolved[TARGET_COLUMN] == "TP").astype(int)

    numeric = [f for f in NUMERIC_FEATURES if f in resolved.columns]
    categorical = [f for f in CATEGORICAL_FEATURES if f in resolved.columns]
    for feature in categorical:
        resolved[feature] = resolved[feature].fillna("NA").astype(str)
    for feature in numeric:
        resolved[feature] = pd.to_numeric(resolved[feature], errors="coerce")

    dev = resolved.loc[resolved["year"] == 2025]
    hold = resolved.loc[resolved["year"] == 2026]
    print(f"dev 2025: {len(dev)} | holdout 2026: {len(hold)} | base WR dev {100 * dev['win'].mean():.1f}% "
          f"hold {100 * hold['win'].mean():.1f}%")

    features = numeric + categorical
    dev_pool = Pool(dev[features], dev["win"], cat_features=categorical)
    model = CatBoostClassifier(
        iterations=300, depth=3, learning_rate=0.05, l2_leaf_reg=10,
        loss_function="Logloss", random_seed=7, verbose=0, allow_writing_files=False,
    )
    # CV temporal dentro de dev (3 folds por orden de fecha) para estimar techo honesto.
    dev_sorted = dev.sort_values("date").reset_index(drop=True)
    fold_size = len(dev_sorted) // 3
    aucs = []
    from sklearn.metrics import roc_auc_score
    for k in range(2):
        train = dev_sorted.iloc[: fold_size * (k + 1)]
        valid = dev_sorted.iloc[fold_size * (k + 1): fold_size * (k + 2)]
        if valid["win"].nunique() < 2:
            continue
        m = model.copy()
        m.fit(Pool(train[features], train["win"], cat_features=categorical))
        aucs.append(roc_auc_score(valid["win"], m.predict_proba(valid[features])[:, 1]))
    print(f"AUC walk-forward dentro de dev: {[f'{a:.3f}' for a in aucs]}")

    model.fit(dev_pool)
    importances = sorted(zip(features, model.get_feature_importance(dev_pool)), key=lambda t: -t[1])
    print("\nTop 12 importancias (dev):")
    for name, value in importances[:12]:
        print(f"  {name:38s} {value:6.2f}")

    # Única mirada al holdout.
    hold_scores = model.predict_proba(hold[features])[:, 1]
    auc_hold = roc_auc_score(hold["win"], hold_scores)
    print(f"\nAUC HOLDOUT 2026: {auc_hold:.3f}")
    hold = hold.assign(score=hold_scores)
    months = hold["month"].nunique() or 1
    print(f"{'corte':>8} {'n':>4} {'tr/mes':>7} {'WR%':>6} {'PF':>6}")
    for pct in (0.5, 0.6, 0.7):
        threshold = np.quantile(hold_scores, pct)
        top = hold.loc[hold["score"] >= threshold]
        n = len(top)
        wins = int(top["win"].sum())
        losses = n - wins
        pf = wins / losses if losses else float("inf")
        print(f"top{100 - pct * 100:3.0f}% {n:4d} {n / months:7.1f} {100 * wins / n if n else 0:6.1f} {pf:6.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
