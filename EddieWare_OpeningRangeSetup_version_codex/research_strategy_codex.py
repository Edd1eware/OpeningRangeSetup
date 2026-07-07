#!/usr/bin/env python3
"""Fresh walk-forward research for the Codex opening-range strategy.

This intentionally does not import any prior analysis.  It consumes only the
causal features_slide sidecars and their forward labels.  Every outer fold is
chronological.  Its confidence threshold is selected on a nested, older
validation slice and then frozen for the next unseen date block.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier


DEFAULT_RESULTS = r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score"
SEED = 20260707

# Compact causal set that can be implemented in the live C# indicator.  Outcome,
# raw date and absolute price columns are deliberately absent.
FEATURES = [
    "break_dir",
    "break_bar_sec",
    "time_weekday",
    "or_size_ticks",
    "or_body_ticks",
    "or_upper_wick",
    "or_lower_wick",
    "or_delta",
    "or_volume",
    "or_vwap_distance",
    "or_speed",
    "or_balance",
    "price_change_1b",
    "price_change_2b",
    "price_change_3b",
    "price_change_5b",
    "price_tick_direction",
    "dist_or_high",
    "dist_or_low",
    "dist_vwap",
    "speed_ticks_per_min",
    "speed_ticks_last_2min",
    "speed_ticks_last_5min",
    "speed_velocity",
    "speed_velocity_change",
    "speed_acceleration",
    "volume_1b",
    "volume_2b",
    "volume_5b",
    "volume_percentile",
    "volume_zscore",
    "volume_ratio",
    "delta_1b",
    "delta_2b",
    "delta_5b",
    "delta_cum",
    "delta_change",
    "delta_slope",
    "delta_acceleration",
    "delta_zscore",
    "imbalance_count",
    "imbalance_buy_count",
    "imbalance_sell_count",
    "imbalance_largest",
    "imbalance_density",
    "footprint_efficiency",
    "absorption_buy",
    "absorption_sell",
    "absorption_ratio",
    "price_efficiency",
    "range_ticks",
    "atr_1m",
    "atr_5m",
    "realized_volatility",
    "vwap_slope",
    "vwap_distance",
    "d_micro_trend_score",
    "d_initiative_score",
    "d_responsive_score",
    "mx_aggressor_ratio_1b",
    "mx_price_impact_ticks_1b",
    "mx_vpin_1b",
    "mx_consecutive_absorption",
    "mx_whale_large_count",
    "mx_whale_concentration",
    "velocity_percentile",
    "velocity_zscore",
    "velocity_slope",
    "volcore_percentile",
    "volcore_zscore",
    "deltacore_percentile",
    "deltacore_zscore",
    "profile_confluence_count",
    "breakout_inside_PREOPEN_value_area",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS)
    parser.add_argument("--output", default="strategy_research_report_codex.json")
    parser.add_argument("--folds", type=int, default=5)
    return parser.parse_args()


def load_slides(results_dir: str) -> pd.DataFrame:
    frames = []
    for path in sorted(glob.glob(os.path.join(results_dir, "features_slide_*_NY.csv"))):
        try:
            frame = pd.read_csv(path)
            frame["_source"] = os.path.basename(path)
            frames.append(frame)
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
            continue
    if not frames:
        raise RuntimeError("No features_slide sidecars found")
    data = pd.concat(frames, ignore_index=True, sort=False)
    data["fecha"] = data["fecha"].astype(str).str[:10]
    data["break_bar_sec"] = pd.to_numeric(data["break_bar_sec"], errors="coerce")
    data = data.sort_values(["fecha", "break_bar_sec"]).reset_index(drop=True)

    first = pd.to_numeric(data["first_hit40"], errors="coerce").fillna(0).astype(int)
    both = (
        pd.to_numeric(data["hit40_up"], errors="coerce").fillna(0).eq(1)
        & pd.to_numeric(data["hit40_dn"], errors="coerce").fillna(0).eq(1)
    )
    # Class 0=no conclusive move, 1=up first, 2=down first.  Same-bar/both-side
    # cases are ambiguous in one-minute data and are conservatively classed as 0.
    data["target"] = np.where(both, 0, np.where(first.eq(1), 1, np.where(first.eq(-1), 2, 0)))
    data["ambiguous_both40"] = both.astype(int)
    return data


def feature_matrix(data: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    available = [name for name in FEATURES if name in data.columns]
    x = data[available].copy()
    categorical = [name for name in ["break_dir"] if name in x.columns]
    for column in categorical:
        x[column] = x[column].fillna("missing").astype(str)
    for column in x.columns:
        if column not in categorical:
            x[column] = pd.to_numeric(x[column], errors="coerce")
    keep = [
        column
        for column in x.columns
        if x[column].notna().mean() >= 0.10 and x[column].nunique(dropna=False) > 1
    ]
    x = x[keep]
    return x, [column for column in categorical if column in keep]


def class_weights(y: np.ndarray) -> list[float]:
    counts = np.bincount(y, minlength=3).astype(float)
    weights = len(y) / np.maximum(1.0, 3.0 * counts)
    return [float(min(8.0, value)) for value in weights]


def fit_model(x: pd.DataFrame, y: np.ndarray, categorical: list[str], seed: int) -> CatBoostClassifier:
    model = CatBoostClassifier(
        loss_function="MultiClass",
        iterations=320,
        depth=4,
        learning_rate=0.035,
        l2_leaf_reg=18.0,
        random_strength=1.0,
        class_weights=class_weights(y),
        random_seed=seed,
        verbose=False,
        allow_writing_files=False,
        thread_count=4,
    )
    model.fit(x, y, cat_features=categorical, verbose=False)
    return model


def choose_trades(rows: pd.DataFrame, probabilities: np.ndarray, threshold: float) -> pd.DataFrame:
    scored = rows[["fecha", "break_bar_sec", "target", "ambiguous_both40"]].copy()
    scored["p_none"] = probabilities[:, 0]
    scored["p_up"] = probabilities[:, 1]
    scored["p_down"] = probabilities[:, 2]
    scored["p_move"] = scored[["p_up", "p_down"]].max(axis=1)
    scored["side_class"] = np.where(scored["p_up"] >= scored["p_down"], 1, 2)
    eligible = scored[scored["p_move"] >= threshold]
    if eligible.empty:
        return eligible
    # Causal policy: act on the first threshold crossing of each date.
    return (
        eligible.sort_values(["fecha", "break_bar_sec"])
        .groupby("fecha", as_index=False, sort=True)
        .first()
    )


def add_pnl(trades: pd.DataFrame, timeout_ticks: float) -> pd.DataFrame:
    output = trades.copy()
    output["outcome"] = np.where(
        output["target"].eq(0),
        "TIMEOUT",
        np.where(output["target"].eq(output["side_class"]), "WIN", "LOSS"),
    )
    output["pnl_ticks"] = np.select(
        [output["outcome"].eq("WIN"), output["outcome"].eq("LOSS")],
        [38.0, -42.0],
        default=float(timeout_ticks),
    )
    return output


def metrics(trades: pd.DataFrame, total_dates: int, timeout_ticks: float = -10.0) -> dict[str, float | int]:
    valued = add_pnl(trades, timeout_ticks)
    positive = valued.loc[valued["pnl_ticks"] > 0, "pnl_ticks"].sum()
    negative = -valued.loc[valued["pnl_ticks"] < 0, "pnl_ticks"].sum()
    terminal = valued[valued["outcome"].isin(["WIN", "LOSS"])]
    streak = 0
    max_streak = 0
    for outcome in valued.sort_values(["fecha", "break_bar_sec"])["outcome"]:
        if outcome == "LOSS":
            streak += 1
            max_streak = max(max_streak, streak)
        elif outcome == "WIN":
            streak = 0
    return {
        "trades": int(len(valued)),
        "dates": int(total_dates),
        "coverage": float(len(valued) / total_dates) if total_dates else math.nan,
        "wins": int(valued["outcome"].eq("WIN").sum()),
        "losses": int(valued["outcome"].eq("LOSS").sum()),
        "timeouts": int(valued["outcome"].eq("TIMEOUT").sum()),
        "terminal_wr": float(terminal["outcome"].eq("WIN").mean()) if len(terminal) else math.nan,
        "profit_factor": float(positive / negative) if negative else math.inf,
        "net_ticks": float(valued["pnl_ticks"].sum()),
        "ticks_per_trade": float(valued["pnl_ticks"].mean()) if len(valued) else math.nan,
        "max_losing_streak": int(max_streak),
    }


def date_folds(dates: np.ndarray, folds: int) -> list[tuple[np.ndarray, np.ndarray]]:
    initial = max(100, int(len(dates) * 0.50))
    boundaries = np.linspace(initial, len(dates), folds + 1, dtype=int)
    return [(dates[: boundaries[i]], dates[boundaries[i] : boundaries[i + 1]]) for i in range(folds)]


def select_threshold(
    train_rows: pd.DataFrame,
    x: pd.DataFrame,
    categorical: list[str],
    seed: int,
) -> float:
    dates = train_rows["fecha"].drop_duplicates().to_numpy()
    cut = max(50, int(len(dates) * 0.72))
    inner_dates, validation_dates = dates[:cut], dates[cut:]
    inner_mask = train_rows["fecha"].isin(inner_dates).to_numpy()
    validation_mask = train_rows["fecha"].isin(validation_dates).to_numpy()
    model = fit_model(
        x.loc[inner_mask],
        train_rows.loc[inner_mask, "target"].to_numpy(dtype=int),
        categorical,
        seed,
    )
    probabilities = model.predict_proba(x.loc[validation_mask])
    validation_rows = train_rows.loc[validation_mask]
    best_threshold = 0.50
    best_score = -math.inf
    for threshold in np.arange(0.25, 0.76, 0.05):
        chosen = choose_trades(validation_rows, probabilities, float(threshold))
        result = metrics(chosen, len(validation_dates), timeout_ticks=-10.0)
        if result["trades"] < max(8, int(len(validation_dates) * 0.15)):
            continue
        # Penalize sparse policies and losing streaks.  No future test data enters here.
        score = (
            result["net_ticks"]
            + 25.0 * result["coverage"]
            - 10.0 * result["max_losing_streak"]
        )
        if score > best_score:
            best_score = score
            best_threshold = float(threshold)
    return best_threshold


def main() -> None:
    args = parse_args()
    data = load_slides(args.results_dir)
    x, categorical = feature_matrix(data)
    dates = data["fecha"].drop_duplicates().to_numpy()
    folds = date_folds(dates, args.folds)
    oos_parts = []
    fold_report = []

    for fold, (train_dates, test_dates) in enumerate(folds, start=1):
        train_mask = data["fecha"].isin(train_dates).to_numpy()
        test_mask = data["fecha"].isin(test_dates).to_numpy()
        train_rows = data.loc[train_mask]
        threshold = select_threshold(
            train_rows,
            x.loc[train_mask],
            categorical,
            SEED + fold,
        )
        model = fit_model(
            x.loc[train_mask],
            train_rows["target"].to_numpy(dtype=int),
            categorical,
            SEED + 100 + fold,
        )
        probabilities = model.predict_proba(x.loc[test_mask])
        selected = choose_trades(data.loc[test_mask], probabilities, threshold)
        selected["fold"] = fold
        selected["threshold"] = threshold
        oos_parts.append(selected)
        fold_report.append(
            {
                "fold": fold,
                "train_start": str(train_dates[0]),
                "train_end": str(train_dates[-1]),
                "test_start": str(test_dates[0]),
                "test_end": str(test_dates[-1]),
                "threshold": threshold,
                **metrics(selected, len(test_dates), timeout_ticks=-10.0),
            }
        )

    oos = pd.concat(oos_parts, ignore_index=True) if oos_parts else pd.DataFrame()
    test_dates_total = sum(len(test) for _, test in folds)
    stress = {
        str(timeout): metrics(oos, test_dates_total, timeout_ticks=float(timeout))
        for timeout in [-2, -10, -20, -40]
    }
    class_counts = data["target"].value_counts().sort_index().to_dict()
    report = {
        "policy": "First per-date minute whose max(P(up-first40), P(down-first40)) crosses a nested walk-forward threshold.",
        "pnl_assumptions": {
            "win_ticks_after_slippage": 38,
            "loss_ticks_after_slippage": -42,
            "ambiguous_both40": "treated as no-conclusive-move",
            "timeout_stress_ticks": [-2, -10, -20, -40],
        },
        "data": {
            "rows": int(len(data)),
            "dates": int(len(dates)),
            "period": [str(dates[0]), str(dates[-1])],
            "class_counts": {str(k): int(v) for k, v in class_counts.items()},
            "ambiguous_rows": int(data["ambiguous_both40"].sum()),
            "features": list(x.columns),
        },
        "folds": fold_report,
        "oos_stress": stress,
    }
    output_path = Path(args.output).resolve()
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
