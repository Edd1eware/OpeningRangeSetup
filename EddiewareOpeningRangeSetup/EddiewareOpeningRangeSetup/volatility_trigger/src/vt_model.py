from __future__ import annotations

import math
from collections import defaultdict
from typing import Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .vt_core import FEATURE_GROUPS


def _pipeline(seed: int) -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=1.0,
                    penalty="l2",
                    class_weight="balanced",
                    max_iter=1000,
                    random_state=seed,
                    solver="lbfgs",
                ),
            ),
        ]
    )


def _weights_by_lb(frame: pd.DataFrame) -> np.ndarray:
    counts = frame.groupby("lb_id")["lb_id"].transform("size").to_numpy()
    return 1.0 / np.maximum(counts, 1)


def _safe_auc(y: np.ndarray, probability: np.ndarray) -> float:
    return (
        float(roc_auc_score(y, probability))
        if len(np.unique(y)) == 2
        else math.nan
    )


def _safe_pr(y: np.ndarray, probability: np.ndarray) -> float:
    return (
        float(average_precision_score(y, probability))
        if np.any(y == 1)
        else math.nan
    )


def expanding_month_folds(frame: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray, str]]:
    dates = pd.to_datetime(frame["session_date"])
    months = dates.dt.to_period("M").astype(str)
    ordered = sorted(months.unique())
    folds: list[tuple[np.ndarray, np.ndarray, str]] = []
    for index in range(2, len(ordered)):
        train_months = set(ordered[:index])
        test_month = ordered[index]
        train = np.flatnonzero(months.isin(train_months).to_numpy())
        test = np.flatnonzero((months == test_month).to_numpy())
        if len(train) and len(test):
            folds.append((train, test, test_month))
    return folds


def cross_validated_predictions(
    frame: pd.DataFrame,
    features: Sequence[str],
    seed: int,
) -> tuple[pd.DataFrame, list[dict[str, float | str | int]]]:
    outputs: list[pd.DataFrame] = []
    fold_rows: list[dict[str, float | str | int]] = []
    y_all = frame["sniper_success"].astype(int).to_numpy()
    for train_indices, test_indices, month in expanding_month_folds(frame):
        train = frame.iloc[train_indices]
        test = frame.iloc[test_indices]
        y_train = y_all[train_indices]
        y_test = y_all[test_indices]
        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            fold_rows.append(
                {
                    "test_month": month,
                    "train_rows": len(train),
                    "test_rows": len(test),
                    "auc": math.nan,
                    "pr_auc": math.nan,
                    "status": "SKIP_SINGLE_CLASS",
                }
            )
            continue
        model = _pipeline(seed)
        model.fit(
            train[list(features)],
            y_train,
            model__sample_weight=_weights_by_lb(train),
        )
        probability = model.predict_proba(test[list(features)])[:, 1]
        output = test[
            [
                "session_date",
                "lb_id",
                "candidate_ticks",
                "candidate_direction",
                "lb_direction",
                "sniper_success",
            ]
        ].copy()
        output["probability"] = probability
        output["test_month"] = month
        outputs.append(output)
        fold_rows.append(
            {
                "test_month": month,
                "train_rows": len(train),
                "test_rows": len(test),
                "train_lbs": int(train["lb_id"].nunique()),
                "test_lbs": int(test["lb_id"].nunique()),
                "auc": _safe_auc(y_test, probability),
                "pr_auc": _safe_pr(y_test, probability),
                "brier": float(brier_score_loss(y_test, probability)),
                "status": "PASS",
            }
        )
    predictions = (
        pd.concat(outputs, ignore_index=True)
        if outputs
        else pd.DataFrame()
    )
    return predictions, fold_rows


def bootstrap_auc_by_lb(
    predictions: pd.DataFrame,
    repetitions: int,
    seed: int,
) -> tuple[float, float, float]:
    if predictions.empty:
        return math.nan, math.nan, math.nan
    groups = {
        lb_id: group
        for lb_id, group in predictions.groupby("lb_id", sort=False)
    }
    ids = np.asarray(list(groups), dtype=object)
    y = predictions["sniper_success"].astype(int).to_numpy()
    probability = predictions["probability"].to_numpy()
    point = _safe_auc(y, probability)
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(repetitions):
        sample = rng.choice(ids, size=len(ids), replace=True)
        parts = [groups[value] for value in sample]
        boot = pd.concat(parts, ignore_index=True)
        boot_y = boot["sniper_success"].astype(int).to_numpy()
        if len(np.unique(boot_y)) < 2:
            continue
        values.append(
            float(roc_auc_score(boot_y, boot["probability"].to_numpy()))
        )
    if not values:
        return point, math.nan, math.nan
    low, high = np.quantile(values, [0.025, 0.975])
    return point, float(low), float(high)


def first_trigger_metrics(
    predictions: pd.DataFrame,
    threshold: float = 0.5,
) -> dict[str, float | int]:
    if predictions.empty:
        return {
            "triggers": 0,
            "coverage": 0.0,
            "precision": math.nan,
            "recall": 0.0,
        }
    selected: list[pd.Series] = []
    for _, group in predictions.groupby("lb_id", sort=False):
        ordered = group.sort_values(
            ["candidate_ticks", "probability"],
            ascending=[True, False],
        )
        for _, time_group in ordered.groupby("candidate_ticks", sort=True):
            best = time_group.sort_values(
                "probability",
                ascending=False,
            ).iloc[0]
            if float(best["probability"]) >= threshold:
                selected.append(best)
                break
    total_lbs = predictions["lb_id"].nunique()
    if not selected:
        return {
            "triggers": 0,
            "coverage": 0.0,
            "precision": math.nan,
            "recall": 0.0,
        }
    chosen = pd.DataFrame(selected)
    positives_available = (
        predictions.groupby("lb_id")["sniper_success"].max().sum()
    )
    return {
        "triggers": int(len(chosen)),
        "coverage": float(len(chosen) / max(total_lbs, 1)),
        "precision": float(chosen["sniper_success"].mean()),
        "recall": float(
            chosen["sniper_success"].sum() / max(positives_available, 1)
        ),
        "median_trigger_delay_ms": float(
            (
                chosen["candidate_ticks"]
                - chosen.groupby("lb_id")["candidate_ticks"].transform("min")
            ).median()
            / 10_000
        ),
    }


def baseline_results(frame: pd.DataFrame, seed: int) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for delay in (0, 100, 250, 500, 1000):
        subset = frame[
            (frame["time_since_lb_ms"] == delay)
            & (frame["candidate_direction"] == frame["lb_direction"])
        ]
        results.append(
            {
                "baseline": f"LB_DIRECTION_DELAY_{delay}MS",
                "triggers": int(len(subset)),
                "lbs": int(subset["lb_id"].nunique()),
                "sniper_precision": float(subset["sniper_success"].mean())
                if len(subset)
                else math.nan,
            }
        )

    velocity_threshold = float(
        frame["base_price_velocity_100ms"].quantile(0.95)
    )
    rate_threshold = float(frame["base_trade_rate_100ms"].quantile(0.95))
    for name, mask in (
        (
            "PRICE_VELOCITY_P95",
            frame["base_price_velocity_100ms"] >= velocity_threshold,
        ),
        (
            "TRADE_RATE_P95",
            frame["base_trade_rate_100ms"] >= rate_threshold,
        ),
        (
            "PRICE_VELOCITY_AND_TRADE_RATE_P95",
            (frame["base_price_velocity_100ms"] >= velocity_threshold)
            & (frame["base_trade_rate_100ms"] >= rate_threshold),
        ),
    ):
        selected: list[pd.Series] = []
        candidates = frame[mask]
        for _, group in candidates.groupby("lb_id", sort=False):
            selected.append(
                group.sort_values(
                    ["candidate_ticks", "base_price_velocity_100ms"],
                    ascending=[True, False],
                ).iloc[0]
            )
        chosen = pd.DataFrame(selected)
        results.append(
            {
                "baseline": name,
                "triggers": int(len(chosen)),
                "lbs": int(chosen["lb_id"].nunique())
                if len(chosen)
                else 0,
                "sniper_precision": float(chosen["sniper_success"].mean())
                if len(chosen)
                else math.nan,
            }
        )

    rng = np.random.default_rng(seed)
    selected = []
    for _, group in frame.groupby("lb_id", sort=False):
        selected.append(group.iloc[int(rng.integers(0, len(group)))])
    random_rows = pd.DataFrame(selected)
    results.append(
        {
            "baseline": "RANDOM_CANDIDATE_DIRECTION",
            "triggers": int(len(random_rows)),
            "lbs": int(random_rows["lb_id"].nunique()),
            "sniper_precision": float(random_rows["sniper_success"].mean()),
        }
    )
    return results


def phenomenon_summary(frame: pd.DataFrame) -> dict[str, object]:
    per_lb = frame.groupby("lb_id", as_index=False).agg(
        session_date=("session_date", "first"),
        has_sniper=("sniper_success", "max"),
    )
    positive = per_lb[per_lb["has_sniper"] == 1].copy()
    positive["month"] = pd.to_datetime(
        positive["session_date"]
    ).dt.to_period("M").astype(str)
    return {
        "liquidity_bursts": int(len(per_lb)),
        "sniper_eligible_bursts": int(len(positive)),
        "sniper_eligible_rate": float(len(positive) / max(len(per_lb), 1)),
        "months_with_sniper_eligible": int(positive["month"].nunique()),
    }


def evaluate_discovery(
    frame: pd.DataFrame,
    config: Mapping[str, object],
) -> dict[str, object]:
    valid = frame[
        (frame["outcome_valid"] == 1)
        & (frame["causality_pass"] == 1)
    ].copy()
    seed = int(config["random_seed"])
    base_features = FEATURE_GROUPS["base"]
    base_predictions, base_folds = cross_validated_predictions(
        valid,
        base_features,
        seed,
    )
    base_by_month = {
        str(row["test_month"]): row for row in base_folds
    }

    family_results: dict[str, dict[str, object]] = {}
    keep: list[str] = []
    gates = config["discovery_gates"]
    for family, family_features in FEATURE_GROUPS.items():
        if family == "base":
            continue
        predictions, folds = cross_validated_predictions(
            valid,
            [*base_features, *family_features],
            seed,
        )
        paired: list[dict[str, float | str]] = []
        for row in folds:
            base = base_by_month.get(str(row["test_month"]))
            if (
                base is None
                or not math.isfinite(float(row.get("auc", math.nan)))
                or not math.isfinite(float(base.get("auc", math.nan)))
            ):
                continue
            auc_lift = float(row["auc"]) - float(base["auc"])
            base_pr = float(base.get("pr_auc", math.nan))
            pr_relative = (
                (float(row["pr_auc"]) - base_pr) / max(base_pr, 1e-12)
                if math.isfinite(base_pr)
                else math.nan
            )
            paired.append(
                {
                    "test_month": str(row["test_month"]),
                    "auc_lift": auc_lift,
                    "pr_relative_lift": pr_relative,
                }
            )
        mean_auc_lift = (
            float(np.mean([row["auc_lift"] for row in paired]))
            if paired
            else math.nan
        )
        mean_pr_lift = (
            float(np.mean([row["pr_relative_lift"] for row in paired]))
            if paired
            else math.nan
        )
        positive_fraction = (
            float(np.mean([row["auc_lift"] > 0 for row in paired]))
            if paired
            else 0.0
        )
        status = (
            "KEEP"
            if (
                math.isfinite(mean_auc_lift)
                and mean_auc_lift >= float(gates["min_incremental_auc"])
                and math.isfinite(mean_pr_lift)
                and mean_pr_lift >= float(gates["min_incremental_pr_relative"])
                and positive_fraction
                >= float(gates["min_positive_fold_fraction"])
            )
            else "DROP"
        )
        if status == "KEEP":
            keep.append(family)
        family_results[family] = {
            "status": status,
            "mean_auc_lift": mean_auc_lift,
            "mean_pr_relative_lift": mean_pr_lift,
            "positive_fold_fraction": positive_fraction,
            "folds": folds,
            "paired_lifts": paired,
        }

    selected_features = list(base_features)
    for family in keep:
        selected_features.extend(FEATURE_GROUPS[family])
    selected_predictions, selected_folds = cross_validated_predictions(
        valid,
        selected_features,
        seed,
    )
    auc, auc_low, auc_high = bootstrap_auc_by_lb(
        selected_predictions,
        int(config["bootstrap_repetitions"]),
        seed,
    )
    y = selected_predictions["sniper_success"].astype(int).to_numpy()
    probability = selected_predictions["probability"].to_numpy()
    candidate_metrics = {
        "auc": auc,
        "auc_ci95": [auc_low, auc_high],
        "pr_auc": _safe_pr(y, probability) if len(y) else math.nan,
        "brier": float(brier_score_loss(y, probability))
        if len(y)
        else math.nan,
        "balanced_accuracy_at_0_5": float(
            balanced_accuracy_score(y, probability >= 0.5)
        )
        if len(np.unique(y)) == 2
        else math.nan,
        "precision_at_0_5": float(
            precision_score(y, probability >= 0.5, zero_division=0)
        )
        if len(y)
        else math.nan,
        "recall_at_0_5": float(
            recall_score(y, probability >= 0.5, zero_division=0)
        )
        if len(y)
        else math.nan,
    }
    phenomenon = phenomenon_summary(valid)
    phenomenon_pass = (
        phenomenon["liquidity_bursts"]
        >= int(gates["min_liquidity_bursts"])
        and phenomenon["sniper_eligible_bursts"]
        >= int(gates["min_sniper_eligible_bursts"])
        and phenomenon["months_with_sniper_eligible"]
        >= int(gates["min_months_with_sniper_eligible"])
    )
    predictive_pass = (
        len(keep) > 0
        and math.isfinite(auc)
        and auc >= float(gates["min_candidate_auc"])
        and math.isfinite(auc_low)
        and auc_low > float(gates["min_auc_ci_low"])
    )
    return {
        "stage": "discovery",
        "phenomenon": phenomenon,
        "phenomenon_pass": phenomenon_pass,
        "base_folds": base_folds,
        "family_results": family_results,
        "selected_families": keep,
        "selected_features": selected_features,
        "selected_folds": selected_folds,
        "candidate_metrics": candidate_metrics,
        "first_trigger_at_0_5": first_trigger_metrics(
            selected_predictions,
            0.5,
        ),
        "baselines": baseline_results(valid, seed),
        "pass": bool(phenomenon_pass and predictive_pass),
        "validation_opened": False,
        "holdout_opened": False,
    }

