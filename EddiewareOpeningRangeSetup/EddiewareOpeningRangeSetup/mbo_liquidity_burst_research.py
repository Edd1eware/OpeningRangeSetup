"""Causal MBO viability research for Liquidity Burst A vs B classification.

Only MBO records with ``ts_event <= causal cutoff`` are predictors.  The script
extracts a rich order-level ledger, joins the pre-existing causal MBP/tape
ledger, evaluates fixed feature sets with leave-one-year-out predictions, and
applies the preregistered purchase gate.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import databento as db
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


WINDOWS = (1, 3, 5, 10)
SCOPES = ("all", "near", "burst", "reference")
FAMILY_A = "A_TRUE_ABSORPTION"
FAMILY_B = "B_CLEAN_BREAKOUT"
ACTION_NAMES = {"A": "add", "C": "cancel", "M": "modify", "T": "trade", "F": "fill"}
REFILL_THRESHOLDS_MS = (10, 50, 100, 250)
LIFETIME_THRESHOLDS_MS = (100, 250, 500)
PERMUTATIONS = 1000
RANDOM_SEED = 20260720

BASELINE_FEATURES = [
    "Profile_Local_Maxima_Count",
    "Previous_Delta_AtEntry",
    "Pre_Approach_Pause_Seconds",
    "Prior_Closed_ATR3_Ticks_AtEntry",
    "Prior_Closed_ATR5_Ticks_AtEntry",
    "Flow_3_5_DirectionalNetDelta",
    "Flow_3_5_GrossAggressive",
    "BuySellRatio",
    "Directional_VWAP_Distance_Ticks_AtEntry",
    "Signal_To_Entry_Latency_Milliseconds",
]

MBP_TAPE_FEATURES = [
    "burst_w1_add_to_aggressive",
    "burst_w1_refill_to_remove",
    "burst_w1_depth_balance",
    "burst_w1_recovery_from_min",
    "burst_w1_refill_latency_ms",
    "burst_w1_aggressive_volume",
    "reference_w3_add_to_aggressive",
    "reference_w3_refill_to_remove",
    "reference_w3_depth_balance",
    "reference_w3_recovery_from_min",
    "reference_w3_refill_latency_ms",
    "reference_w3_aggressive_volume",
]

# Frozen before observing A/B associations.  These are the only MBO predictors
# used by the purchase-gate model; the full ledger remains available for audit.
CORE_MBO_FEATURES = [
    "burst_w1_passive_add_size",
    "burst_w1_passive_pure_cancel_size",
    "burst_w1_passive_fill_size",
    "burst_w1_new_order_survival_share",
    "burst_w1_short_lived_250ms_share",
    "burst_w1_refill_100ms_share",
    "burst_w3_cancel_to_add_size",
    "near_w1_add_size_side_imbalance",
    "near_w1_pure_cancel_size_side_imbalance",
    "near_w1_fill_size_side_imbalance",
    "near_w3_orderbook_message_rate",
    "near_w3_reuse_order_id_share",
]

# Frozen interpretation of the 12 predictors after the direct MBO capability
# audit.  This is reporting metadata, not an additional feature family.
CORE_MBO_FEATURE_STATUS = {
    "burst_w1_passive_add_size": ("EXPLICIT", "A size at the displayed burst-side level"),
    "burst_w1_passive_pure_cancel_size": (
        "INFERRED_DEFENSIBLE",
        "C with no F for the same order/exchange-time/price; economic intent is not observed",
    ),
    "burst_w1_passive_fill_size": ("EXPLICIT", "F size of resting orders; never added to T size"),
    "burst_w1_new_order_survival_share": (
        "INFERRED_RIGHT_CENSORED",
        "Only orders whose A is observed inside the downloaded window",
    ),
    "burst_w1_short_lived_250ms_share": (
        "INFERRED_COMPLETE_CYCLES_ONLY",
        "Only cycles beginning with an observed A and ending before cutoff",
    ),
    "burst_w1_refill_100ms_share": (
        "INFERRED_LEVEL_REPLENISHMENT",
        "A at the same side/price after removal; does not prove same participant",
    ),
    "burst_w3_cancel_to_add_size": (
        "INFERRED_CANCEL_EXPLICIT_ADD",
        "C cause inferred; A explicit; no initial-book denominator",
    ),
    "near_w1_add_size_side_imbalance": ("EXPLICIT_DERIVED", "A sizes by displayed side"),
    "near_w1_pure_cancel_size_side_imbalance": (
        "INFERRED_DEFENSIBLE",
        "C without same-key F, compared by side",
    ),
    "near_w1_fill_size_side_imbalance": ("EXPLICIT_DERIVED", "F sizes by resting side"),
    "near_w3_orderbook_message_rate": (
        "MIXED_EXPLICIT_INFERRED",
        "A/M explicit plus inferred pure-C count",
    ),
    "near_w3_reuse_order_id_share": (
        "EXPLICIT_WINDOW_ONLY",
        "Repeated observed messages per ID; not participant identity",
    ),
}


def safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator > 0 else np.nan


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) == 0 or len(b) == 0:
        return np.nan
    return float((np.greater.outer(a, b).sum() - np.less.outer(a, b).sum()) / (len(a) * len(b)))


def bh_adjust(p_values: pd.Series) -> pd.Series:
    valid = p_values.dropna().sort_values()
    result = pd.Series(np.nan, index=p_values.index, dtype=float)
    if valid.empty:
        return result
    raw = valid.to_numpy() * len(valid) / np.arange(1, len(valid) + 1)
    result.loc[valid.index] = np.minimum.accumulate(raw[::-1])[::-1].clip(max=1)
    return result


def mark_pure_cancels(frame: pd.DataFrame) -> pd.DataFrame:
    """Classify C conservatively against grouped F records.

    CME can emit several unit F records followed by one aggregate C, so a
    row-for-row match is invalid.  ``pure_cancel`` is true only when no F
    exists for the same order, exchange timestamp, and price.  Quantity
    mismatches remain ambiguous and are excluded from pure cancellations.
    """
    frame = frame.copy()
    frame["fill_cancel_relation"] = "NOT_APPLICABLE"
    relevant = frame["action"].isin(["F", "C"])
    keys = ["order_id", "ts_event", "price"]
    grouped = (
        frame.loc[relevant]
        .groupby([*keys, "action"], sort=False)["size"]
        .sum()
        .unstack("action")
        .fillna(0.0)
        .astype(float)
    )
    if "F" not in grouped:
        grouped["F"] = 0.0
    if "C" not in grouped:
        grouped["C"] = 0.0
    grouped["relation"] = np.select(
        [
            grouped["F"].gt(0) & grouped["C"].gt(0) & np.isclose(grouped["F"], grouped["C"]),
            grouped["F"].gt(0) & grouped["C"].gt(0),
            grouped["F"].gt(0),
            grouped["C"].gt(0),
        ],
        [
            "EXACT_GROUP_FILL_C_MATCH",
            "AMBIGUOUS_FILL_C_QUANTITY_MISMATCH",
            "FILL_WITHOUT_C_SAME_KEY",
            "C_WITHOUT_FILL_SAME_KEY",
        ],
        default="NOT_APPLICABLE",
    )
    if relevant.any():
        relation_lookup = grouped["relation"]
        event_keys = pd.MultiIndex.from_frame(frame.loc[relevant, keys])
        frame.loc[relevant, "fill_cancel_relation"] = relation_lookup.reindex(event_keys).to_numpy()
    frame["pure_cancel"] = (
        frame["action"].eq("C")
        & frame["fill_cancel_relation"].eq("C_WITHOUT_FILL_SAME_KEY")
    )
    return frame


def load_causal_mbo(path: Path, cutoff: pd.Timestamp) -> tuple[pd.DataFrame, int]:
    frame = db.DBNStore.from_file(path).to_df()
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    frame["ts_event"] = pd.to_datetime(frame["ts_event"], utc=True)
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["size"] = pd.to_numeric(frame["size"], errors="coerce").fillna(0.0).astype(float)
    frame["raw_ordinal"] = np.arange(len(frame), dtype=np.int64)
    frame = frame.sort_values(
        ["ts_event", "sequence", "raw_ordinal"], kind="stable"
    ).reset_index(drop=True)
    raw_rows = len(frame)
    frame = frame.loc[frame["ts_event"].le(cutoff)].copy().reset_index(drop=True)
    frame["sequence_index_local"] = np.arange(len(frame))
    frame = mark_pure_cancels(frame)
    if frame.empty:
        raise ValueError(f"No causal MBO rows in {path}")
    return frame, raw_rows - len(frame)


def scope_mask(frame: pd.DataFrame, scope: str, burst_price: float, reference: float) -> pd.Series:
    if scope == "all":
        return pd.Series(True, index=frame.index)
    if scope == "near":
        return frame["price"].sub(burst_price).abs().le(1.0)
    if scope == "burst":
        return pd.Series(np.isclose(frame["price"], burst_price, equal_nan=False), index=frame.index)
    if scope == "reference":
        return pd.Series(np.isclose(frame["price"], reference, equal_nan=False), index=frame.index)
    raise ValueError(f"Unknown MBO scope: {scope}")


def _order_lifecycle_features(
    window: pd.DataFrame,
    full: pd.DataFrame,
    order_events: dict[int, pd.DataFrame] | None = None,
) -> dict[str, float]:
    additions = window.loc[window["action"].eq("A")].sort_values("sequence_index_local")
    first_adds = additions.drop_duplicates("order_id", keep="first")
    added_count = len(first_adds)
    if added_count == 0:
        return {
            "new_order_count": 0.0,
            "new_order_survival_share": np.nan,
            "new_order_surviving_size_share": np.nan,
            "new_order_multi_event_share": np.nan,
            "repeated_add_order_id_share": np.nan,
            "median_observed_lifetime_ms": np.nan,
            "mean_observed_lifetime_ms": np.nan,
            **{f"short_lived_{threshold}ms_share": np.nan for threshold in LIFETIME_THRESHOLDS_MS},
        }

    repeated_add_share = safe_ratio(int(additions["order_id"].duplicated(keep=False).groupby(additions["order_id"]).any().sum()), additions["order_id"].nunique())
    if order_events is None:
        order_events = {int(order_id): group for order_id, group in full.groupby("order_id", sort=False)}
    survived = []
    initial_sizes = []
    surviving_sizes = []
    lifetimes = []
    multi_event = []
    empty_history = full.head(0)
    for add in first_adds.itertuples(index=False):
        history = order_events.get(int(add.order_id), empty_history)
        later = history.loc[history["sequence_index_local"].gt(add.sequence_index_local)]
        remaining = float(add.size)
        exit_time = None
        for event in later.itertuples(index=False):
            if event.action == "F":
                remaining -= float(event.size)
            elif bool(event.pure_cancel):
                remaining -= float(event.size)
            elif event.action == "M":
                remaining = float(event.size)
            if remaining <= 0:
                exit_time = event.ts_event
                remaining = 0.0
                break
        initial_sizes.append(float(add.size))
        surviving_sizes.append(max(remaining, 0.0))
        survived.append(exit_time is None and remaining > 0)
        multi_event.append(not later.empty)
        if exit_time is not None:
            lifetimes.append((exit_time - add.ts_event).total_seconds() * 1000)

    lifetimes_array = np.asarray(lifetimes, dtype=float)
    return {
        "new_order_count": float(added_count),
        "new_order_survival_share": float(np.mean(survived)),
        "new_order_surviving_size_share": safe_ratio(sum(surviving_sizes), sum(initial_sizes)),
        "new_order_multi_event_share": float(np.mean(multi_event)),
        "repeated_add_order_id_share": repeated_add_share,
        "median_observed_lifetime_ms": float(np.median(lifetimes_array)) if len(lifetimes_array) else np.nan,
        "mean_observed_lifetime_ms": float(np.mean(lifetimes_array)) if len(lifetimes_array) else np.nan,
        **{
            f"short_lived_{threshold}ms_share": float(np.mean(lifetimes_array <= threshold)) if len(lifetimes_array) else 0.0
            for threshold in LIFETIME_THRESHOLDS_MS
        },
    }


def _refill_features(window: pd.DataFrame) -> dict[str, float]:
    additions = window.loc[window["action"].eq("A") & window["price"].notna()].copy()
    removals = window.loc[(window["action"].eq("F") | window["pure_cancel"]) & window["price"].notna()].copy()
    result: dict[str, float] = {"removal_event_count": float(len(removals))}
    if removals.empty:
        for threshold in REFILL_THRESHOLDS_MS:
            result[f"refill_{threshold}ms_count"] = 0.0
            result[f"refill_{threshold}ms_share"] = np.nan
            result[f"refill_{threshold}ms_size_to_removed"] = np.nan
        return result

    grouped_adds: dict[tuple[str, float], tuple[np.ndarray, np.ndarray]] = {}
    for key, group in additions.groupby(["side", "price"], sort=False):
        ordered = group.sort_values("ts_event")
        grouped_adds[(str(key[0]), float(key[1]))] = (
            np.fromiter((timestamp.value for timestamp in ordered["ts_event"]), dtype=np.int64),
            ordered["size"].to_numpy(dtype=float),
        )

    deltas = []
    next_sizes = []
    removed_sizes = []
    for removal in removals.itertuples(index=False):
        group = grouped_adds.get((str(removal.side), float(removal.price)))
        if group is None:
            deltas.append(np.inf)
            next_sizes.append(0.0)
        else:
            times, sizes = group
            timestamp = int(removal.ts_event.value)
            position = int(np.searchsorted(times, timestamp, side="right"))
            if position >= len(times):
                deltas.append(np.inf)
                next_sizes.append(0.0)
            else:
                deltas.append((times[position] - timestamp) / 1_000_000.0)
                next_sizes.append(float(sizes[position]))
        removed_sizes.append(float(removal.size))

    deltas_array = np.asarray(deltas)
    next_sizes_array = np.asarray(next_sizes)
    removed_sizes_array = np.asarray(removed_sizes)
    for threshold in REFILL_THRESHOLDS_MS:
        matched = deltas_array <= threshold
        result[f"refill_{threshold}ms_count"] = float(matched.sum())
        result[f"refill_{threshold}ms_share"] = float(matched.mean())
        result[f"refill_{threshold}ms_size_to_removed"] = safe_ratio(next_sizes_array[matched].sum(), removed_sizes_array.sum())
    return result


def aggregate_window(
    full: pd.DataFrame,
    window: pd.DataFrame,
    *,
    window_seconds: int,
    passive_side: str,
    order_events: dict[int, pd.DataFrame] | None = None,
    include_order_details: bool = True,
) -> dict[str, float]:
    result: dict[str, float] = {
        "event_count": float(len(window)),
        "event_size": float(window["size"].sum()),
        "unique_order_ids": float(window["order_id"].nunique()),
    }
    id_counts = window["order_id"].value_counts()
    result["reuse_order_id_share"] = safe_ratio(int(id_counts.gt(1).sum()), len(id_counts))
    result["message_rate"] = len(window) / window_seconds

    opposite_side = "B" if passive_side == "A" else "A"
    for code, name in ACTION_NAMES.items():
        action = window.loc[window["action"].eq(code)]
        result[f"{name}_count"] = float(len(action))
        result[f"{name}_size"] = float(action["size"].sum())
        passive = action.loc[action["side"].eq(passive_side)]
        opposite = action.loc[action["side"].eq(opposite_side)]
        result[f"passive_{name}_count"] = float(len(passive))
        result[f"opposite_{name}_count"] = float(len(opposite))
        result[f"passive_{name}_size"] = float(passive["size"].sum())
        result[f"opposite_{name}_size"] = float(opposite["size"].sum())
        result[f"{name}_count_side_imbalance"] = safe_ratio(len(passive) - len(opposite), len(passive) + len(opposite))
        result[f"{name}_size_side_imbalance"] = safe_ratio(passive["size"].sum() - opposite["size"].sum(), passive["size"].sum() + opposite["size"].sum())

    pure_cancel = window.loc[window["pure_cancel"]]
    passive_cancel = pure_cancel.loc[pure_cancel["side"].eq(passive_side)]
    opposite_cancel = pure_cancel.loc[pure_cancel["side"].eq(opposite_side)]
    result.update({
        "pure_cancel_count": float(len(pure_cancel)),
        "pure_cancel_size": float(pure_cancel["size"].sum()),
        "passive_pure_cancel_count": float(len(passive_cancel)),
        "opposite_pure_cancel_count": float(len(opposite_cancel)),
        "passive_pure_cancel_size": float(passive_cancel["size"].sum()),
        "opposite_pure_cancel_size": float(opposite_cancel["size"].sum()),
        "pure_cancel_count_side_imbalance": safe_ratio(len(passive_cancel) - len(opposite_cancel), len(passive_cancel) + len(opposite_cancel)),
        "pure_cancel_size_side_imbalance": safe_ratio(passive_cancel["size"].sum() - opposite_cancel["size"].sum(), passive_cancel["size"].sum() + opposite_cancel["size"].sum()),
        "cancel_to_add_count": safe_ratio(len(pure_cancel), result["add_count"]),
        "cancel_to_add_size": safe_ratio(pure_cancel["size"].sum(), result["add_size"]),
        "fill_to_add_size": safe_ratio(result["fill_size"], result["add_size"]),
        "modify_to_add_count": safe_ratio(result["modify_count"], result["add_count"]),
        "orderbook_message_rate": (result["add_count"] + len(pure_cancel) + result["modify_count"]) / window_seconds,
        "orderbook_size_churn_rate": (result["add_size"] + pure_cancel["size"].sum() + result["modify_size"]) / window_seconds,
    })
    if include_order_details:
        result.update(_order_lifecycle_features(window, full, order_events))
        result.update(_refill_features(window))
    return result


def extract_event_features(row: pd.Series, mbo_dir: Path) -> dict[str, object]:
    cutoff = pd.Timestamp(row["causal_cutoff_utc_inclusive"])
    path = mbo_dir / f"{row['request_id']}.mbo.dbn.zst"
    if not path.exists():
        raise FileNotFoundError(path)
    full, post_cutoff_rows = load_causal_mbo(path, cutoff)
    order_events = {int(order_id): group for order_id, group in full.groupby("order_id", sort=False)}
    burst_price = float(row["burst_price"])
    reference = float(row["reference_level"])
    passive_side = "A" if str(row["burst_side"]).upper() == "BUY" else "B"
    result: dict[str, object] = {
        "request_id": row["request_id"],
        "fecha": row["fecha"],
        "BurstId": row["BurstId"],
        "split": row["split"],
        "family": row["family_label_only"],
        "burst_side": row["burst_side"],
        "burst_price": burst_price,
        "reference_level": reference,
        "causal_cutoff_utc": cutoff.isoformat(),
        "mbo_file": str(path),
        "mbo_causal_rows": float(len(full)),
        "mbo_post_cutoff_rows_excluded": float(post_cutoff_rows),
        "mbo_first_ts_event": full["ts_event"].min().isoformat(),
        "mbo_last_ts_event": full["ts_event"].max().isoformat(),
        "mbo_causal_max_ok": float(full["ts_event"].max() <= cutoff),
        "mbo_unique_order_ids": float(full["order_id"].nunique()),
        "mbo_first_action_add_share": float(
            full.groupby("order_id", sort=False)["action"].first().eq("A").mean()
        ),
        "mbo_left_censored_order_share": float(
            full.groupby("order_id", sort=False)["action"].first().ne("A").mean()
        ),
        "mbo_snapshot_rows": float(((pd.to_numeric(full["flags"], errors="coerce").fillna(0).astype(int) & 32) != 0).sum()),
        "mbo_bad_book_rows": float(((pd.to_numeric(full["flags"], errors="coerce").fillna(0).astype(int) & 4) != 0).sum()),
        "mbo_pure_cancel_rows": float(full["pure_cancel"].sum()),
        "mbo_ambiguous_cancel_fill_rows": float(
            (
                full["action"].eq("C")
                & full["fill_cancel_relation"].eq("AMBIGUOUS_FILL_C_QUANTITY_MISMATCH")
            ).sum()
        ),
    }
    for scope in SCOPES:
        scoped = full.loc[scope_mask(full, scope, burst_price, reference)].copy()
        for seconds in WINDOWS:
            start = cutoff - pd.Timedelta(seconds=seconds)
            window = scoped.loc[scoped["ts_event"].ge(start)].copy()
            values = aggregate_window(
                full,
                window,
                window_seconds=seconds,
                passive_side=passive_side,
                order_events=order_events,
                include_order_details=scope != "all",
            )
            result.update({f"{scope}_w{seconds}_{name}": value for name, value in values.items()})
    return result


def extract_ledger(manifest: pd.DataFrame, mbp_ledger: pd.DataFrame, mbo_dir: Path) -> pd.DataFrame:
    metadata = mbp_ledger[["BurstId", "burst_side", "burst_price", "reference_level"]].drop_duplicates("BurstId")
    joined = manifest.merge(metadata, on="BurstId", how="left", validate="one_to_one")
    if joined[["burst_side", "burst_price", "reference_level"]].isna().any().any():
        raise ValueError("Missing MBP metadata for one or more MBO requests")
    return pd.DataFrame([extract_event_features(row, mbo_dir) for _, row in joined.iterrows()])


def join_existing_features(mbo: pd.DataFrame, mbp: pd.DataFrame, engineered: pd.DataFrame) -> pd.DataFrame:
    existing_columns = [name for name in BASELINE_FEATURES if name in engineered.columns]
    mbp_columns = [name for name in MBP_TAPE_FEATURES if name in mbp.columns]
    frame = mbo.merge(mbp[["BurstId", *mbp_columns]], on="BurstId", how="left", validate="one_to_one")
    frame = frame.merge(engineered[["BurstId", *existing_columns]], on="BurstId", how="left", validate="one_to_one")
    frame["year"] = pd.to_datetime(frame["fecha"]).dt.year
    frame["target"] = frame["family"].eq(FAMILY_A).astype(int)
    return frame


def make_model() -> object:
    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(C=0.2, class_weight="balanced", solver="liblinear", max_iter=3000, random_state=RANDOM_SEED),
    )


def usable_columns(train: pd.DataFrame, columns: list[str]) -> list[str]:
    usable = []
    for column in columns:
        values = pd.to_numeric(train[column], errors="coerce")
        if values.notna().sum() >= 3 and values.dropna().nunique() >= 2:
            usable.append(column)
    if not usable:
        raise ValueError("No usable predictors in training fold")
    return usable


def loyo_predictions(frame: pd.DataFrame, columns: list[str], target: pd.Series | None = None) -> pd.DataFrame:
    y = frame["target"] if target is None else pd.Series(target.to_numpy(), index=frame.index)
    output = []
    for year in sorted(frame["year"].unique()):
        train_mask = frame["year"].ne(year)
        test_mask = frame["year"].eq(year)
        selected = usable_columns(frame.loc[train_mask], columns)
        model = make_model()
        model.fit(frame.loc[train_mask, selected], y.loc[train_mask])
        probability = model.predict_proba(frame.loc[test_mask, selected])[:, 1]
        for index, value in zip(frame.index[test_mask], probability, strict=True):
            output.append({"index": int(index), "probability": float(value), "test_year": int(year), "feature_count": len(selected)})
    predictions = pd.DataFrame(output).set_index("index").sort_index()
    predictions["target"] = y.loc[predictions.index].astype(int)
    predictions["burst_side"] = frame.loc[predictions.index, "burst_side"]
    predictions["BurstId"] = frame.loc[predictions.index, "BurstId"]
    return predictions


def auc_or_nan(y: pd.Series, probability: pd.Series) -> float:
    return float(roc_auc_score(y, probability)) if y.nunique() == 2 else np.nan


def evaluate_feature_sets(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, list[str]]]:
    existing = [name for name in BASELINE_FEATURES + MBP_TAPE_FEATURES if name in frame.columns]
    mbo = [name for name in CORE_MBO_FEATURES if name in frame.columns]
    if len(mbo) != len(CORE_MBO_FEATURES):
        raise ValueError(f"Missing frozen MBO features: {sorted(set(CORE_MBO_FEATURES) - set(mbo))}")
    sets = {
        "EXISTING_CAUSAL": existing,
        "MBO_ONLY": mbo,
        "EXISTING_CAUSAL_PLUS_MBO": existing + mbo,
    }
    metric_rows = []
    prediction_rows = []
    for name, columns in sets.items():
        predictions = loyo_predictions(frame, columns)
        predictions["feature_set"] = name
        prediction_rows.append(predictions.reset_index())
        metric_rows.append({"feature_set": name, "subgroup": "ALL", "n": len(predictions), "roc_auc": auc_or_nan(predictions["target"], predictions["probability"])})
        for year, group in predictions.groupby("test_year"):
            metric_rows.append({"feature_set": name, "subgroup": f"YEAR_{year}", "n": len(group), "roc_auc": auc_or_nan(group["target"], group["probability"])})
        for side, group in predictions.groupby("burst_side"):
            metric_rows.append({"feature_set": name, "subgroup": f"SIDE_{side}", "n": len(group), "roc_auc": auc_or_nan(group["target"], group["probability"])})
    return pd.DataFrame(metric_rows), pd.concat(prediction_rows, ignore_index=True), sets


def permutation_test(frame: pd.DataFrame, sets: dict[str, list[str]], observed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    observed_auc = observed.loc[observed["subgroup"].eq("ALL")].set_index("feature_set")["roc_auc"]
    observed_delta = float(observed_auc["EXISTING_CAUSAL_PLUS_MBO"] - observed_auc["EXISTING_CAUSAL"])
    rng = np.random.default_rng(RANDOM_SEED)
    rows = []
    for iteration in range(PERMUTATIONS):
        permuted = frame["target"].copy()
        for _, indexes in frame.groupby("year").groups.items():
            permuted.loc[indexes] = rng.permutation(permuted.loc[indexes].to_numpy())
        aucs = {}
        for name, columns in sets.items():
            predictions = loyo_predictions(frame, columns, target=permuted)
            aucs[name] = auc_or_nan(predictions["target"], predictions["probability"])
        rows.append({
            "iteration": iteration,
            **{f"auc_{name}": value for name, value in aucs.items()},
            "delta_plus_mbo": aucs["EXISTING_CAUSAL_PLUS_MBO"] - aucs["EXISTING_CAUSAL"],
        })
    distribution = pd.DataFrame(rows)
    summary = pd.DataFrame([
        {
            "test": "MBO_ONLY_AUC",
            "observed": float(observed_auc["MBO_ONLY"]),
            "null_reference": 0.5,
            "p_permutation": float((1 + distribution["auc_MBO_ONLY"].ge(observed_auc["MBO_ONLY"]).sum()) / (PERMUTATIONS + 1)),
        },
        {
            "test": "DELTA_EXISTING_PLUS_MBO",
            "observed": observed_delta,
            "null_reference": 0.0,
            "p_permutation": float((1 + distribution["delta_plus_mbo"].ge(observed_delta).sum()) / (PERMUTATIONS + 1)),
        },
    ])
    return summary, distribution


def univariate_stability(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for feature in CORE_MBO_FEATURES:
        a = pd.to_numeric(frame.loc[frame["target"].eq(1), feature], errors="coerce").dropna().to_numpy()
        b = pd.to_numeric(frame.loc[frame["target"].eq(0), feature], errors="coerce").dropna().to_numpy()
        p = mannwhitneyu(a, b, alternative="two-sided").pvalue if len(a) >= 3 and len(b) >= 3 else np.nan
        global_difference = np.nanmedian(a) - np.nanmedian(b) if len(a) and len(b) else np.nan
        signs: dict[str, float] = {}
        for year, group in frame.groupby("year"):
            av = pd.to_numeric(group.loc[group["target"].eq(1), feature], errors="coerce").dropna()
            bv = pd.to_numeric(group.loc[group["target"].eq(0), feature], errors="coerce").dropna()
            signs[f"sign_year_{year}"] = float(np.sign(av.median() - bv.median())) if len(av) >= 3 and len(bv) >= 3 else np.nan
        for side, group in frame.groupby("burst_side"):
            av = pd.to_numeric(group.loc[group["target"].eq(1), feature], errors="coerce").dropna()
            bv = pd.to_numeric(group.loc[group["target"].eq(0), feature], errors="coerce").dropna()
            signs[f"sign_side_{side}"] = float(np.sign(av.median() - bv.median())) if len(av) >= 3 and len(bv) >= 3 else np.nan
        target_sign = float(np.sign(global_difference)) if np.isfinite(global_difference) else np.nan
        year_values = [value for key, value in signs.items() if key.startswith("sign_year_")]
        side_values = [value for key, value in signs.items() if key.startswith("sign_side_")]
        rows.append({
            "feature": feature,
            "coverage_pct": 100 * pd.to_numeric(frame[feature], errors="coerce").notna().mean(),
            "median_A": float(np.nanmedian(a)) if len(a) else np.nan,
            "median_B": float(np.nanmedian(b)) if len(b) else np.nan,
            "cliffs_delta_A_minus_B": cliffs_delta(a, b),
            "mann_whitney_p": p,
            "global_sign": target_sign,
            "stable_all_years": int(np.isfinite(target_sign) and target_sign != 0 and len(year_values) == 3 and all(value == target_sign for value in year_values)),
            "stable_both_sides": int(np.isfinite(target_sign) and target_sign != 0 and len(side_values) == 2 and all(value == target_sign for value in side_values)),
            **signs,
        })
    result = pd.DataFrame(rows)
    result["q_bh"] = bh_adjust(result["mann_whitney_p"])
    result["gate_robust_feature"] = (
        result["q_bh"].le(0.20)
        & result["cliffs_delta_A_minus_B"].abs().ge(0.33)
        & result["stable_all_years"].eq(1)
        & result["stable_both_sides"].eq(1)
    ).astype(int)
    return result.sort_values(["gate_robust_feature", "q_bh"], ascending=[False, True], na_position="last").reset_index(drop=True)


def apply_gate(metrics: pd.DataFrame, permutations: pd.DataFrame, univariate: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    table = metrics.pivot(index="subgroup", columns="feature_set", values="roc_auc")
    mbo_all = float(table.loc["ALL", "MBO_ONLY"])
    delta_all = float(table.loc["ALL", "EXISTING_CAUSAL_PLUS_MBO"] - table.loc["ALL", "EXISTING_CAUSAL"])
    p_delta = float(permutations.loc[permutations["test"].eq("DELTA_EXISTING_PLUS_MBO"), "p_permutation"].iloc[0])
    year_deltas = []
    for year in (2022, 2023, 2024):
        year_deltas.append(float(table.loc[f"YEAR_{year}", "EXISTING_CAUSAL_PLUS_MBO"] - table.loc[f"YEAR_{year}", "EXISTING_CAUSAL"]))
    buy_auc = float(table.loc["SIDE_BUY", "MBO_ONLY"])
    sell_auc = float(table.loc["SIDE_SELL", "MBO_ONLY"])
    robust_count = int(univariate["gate_robust_feature"].sum())
    checks = [
        ("MBO_ONLY_AUC_AT_LEAST_0_65", mbo_all, 0.65, mbo_all >= 0.65),
        ("DELTA_AUC_AT_LEAST_0_08", delta_all, 0.08, delta_all >= 0.08),
        ("DELTA_PERMUTATION_P_AT_MOST_0_10", p_delta, 0.10, p_delta <= 0.10),
        ("AT_LEAST_TWO_YEARS_NONNEGATIVE_DELTA", sum(value >= 0 for value in year_deltas), 2, sum(value >= 0 for value in year_deltas) >= 2),
        ("NO_YEAR_DELTA_BELOW_MINUS_0_05", min(year_deltas), -0.05, min(year_deltas) >= -0.05),
        ("BUY_MBO_AUC_AT_LEAST_0_55", buy_auc, 0.55, buy_auc >= 0.55),
        ("SELL_MBO_AUC_AT_LEAST_0_55", sell_auc, 0.55, sell_auc >= 0.55),
        ("AT_LEAST_ONE_ROBUST_COMPACT_FEATURE", robust_count, 1, robust_count >= 1),
    ]
    frame = pd.DataFrame(checks, columns=["criterion", "observed", "threshold", "passed"])
    return frame, bool(frame["passed"].all())


def create_plots(output: Path, frame: pd.DataFrame, metrics: pd.DataFrame, predictions: pd.DataFrame, univariate: pd.DataFrame) -> list[str]:
    folder = output / "visualizations"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []

    plot = univariate.sort_values("cliffs_delta_A_minus_B").copy()
    colors = ["#2c7fb8" if value >= 0 else "#d95f0e" for value in plot["cliffs_delta_A_minus_B"]]
    plt.figure(figsize=(11, 7))
    plt.barh(plot["feature"], plot["cliffs_delta_A_minus_B"], color=colors)
    plt.axvline(0, color="black", linewidth=0.8)
    plt.xlabel("Cliff delta (A absorción − B breakout)")
    plt.title("Features MBO compactas — efecto discovery")
    plt.tight_layout()
    path = folder / "mbo_compact_feature_effects.png"
    plt.savefig(path, dpi=160)
    plt.close()
    paths.append(str(path))

    pivot = metrics.pivot(index="subgroup", columns="feature_set", values="roc_auc")
    order = ["ALL", "YEAR_2022", "YEAR_2023", "YEAR_2024", "SIDE_BUY", "SIDE_SELL"]
    pivot = pivot.loc[order]
    ax = pivot.plot(kind="bar", figsize=(11, 6), ylim=(0, 1), color=["#666666", "#2c7fb8", "#31a354"])
    ax.axhline(0.5, color="black", linestyle="--", linewidth=1)
    ax.set_ylabel("ROC AUC LOYO")
    ax.set_title("Información incremental MBO y estabilidad")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    path = folder / "loyo_auc_stability.png"
    plt.savefig(path, dpi=160)
    plt.close()
    paths.append(str(path))

    plt.figure(figsize=(8, 7))
    for name, group in predictions.groupby("feature_set"):
        fpr, tpr, _ = roc_curve(group["target"], group["probability"])
        auc = roc_auc_score(group["target"], group["probability"])
        plt.plot(fpr, tpr, label=f"{name} AUC={auc:.3f}")
    plt.plot([0, 1], [0, 1], "k--", linewidth=1)
    plt.xlabel("False positive rate")
    plt.ylabel("True positive rate")
    plt.title("Predicciones fuera de año")
    plt.legend(fontsize=8)
    plt.tight_layout()
    path = folder / "loyo_roc.png"
    plt.savefig(path, dpi=160)
    plt.close()
    paths.append(str(path))
    return paths


def write_report(output: Path, frame: pd.DataFrame, metrics: pd.DataFrame, permutations: pd.DataFrame, univariate: pd.DataFrame, gate: pd.DataFrame, gate_passed: bool) -> None:
    overall = metrics.loc[metrics["subgroup"].eq("ALL")].set_index("feature_set")["roc_auc"]
    delta = overall["EXISTING_CAUSAL_PLUS_MBO"] - overall["EXISTING_CAUSAL"]
    p_delta = permutations.loc[permutations["test"].eq("DELTA_EXISTING_PLUS_MBO"), "p_permutation"].iloc[0]
    lines = [
        "# Resultado piloto MBO — Liquidity Burst",
        "",
        "## Decisión",
        "",
        f"Puerta de compra: **{'PASÓ' if gate_passed else 'NO PASÓ'}**.",
        f"Por tanto: **{'se permite comprar discovery restante' if gate_passed else 'se detienen las compras de MBO'}**.",
        "",
        "## Resultado primario",
        "",
        f"- Eventos/días: {len(frame)} (15 A, 15 B).",
        f"- AUC LOYO baseline causal: {overall['EXISTING_CAUSAL']:.3f}.",
        f"- AUC LOYO MBO-only: {overall['MBO_ONLY']:.3f}.",
        f"- AUC LOYO baseline + MBO: {overall['EXISTING_CAUSAL_PLUS_MBO']:.3f}.",
        f"- Mejora incremental: {delta:+.3f}.",
        f"- p de permutación para la mejora: {p_delta:.4f} ({PERMUTATIONS} permutaciones dentro de año).",
        "",
        "## Puerta congelada",
        "",
        "| Criterio | Observado | Umbral | Pasó |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in gate.itertuples(index=False):
        lines.append(f"| {row.criterion} | {row.observed:.4f} | {row.threshold:.4f} | {int(row.passed)} |")
    lines.extend([
        "",
        "## Features compactas",
        "",
        "| Feature | Cobertura | Cliff A-B | q BH | Años estable | Lados estable | Robusta |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in univariate.itertuples(index=False):
        lines.append(f"| {row.feature} | {row.coverage_pct:.1f}% | {row.cliffs_delta_A_minus_B:.3f} | {row.q_bh:.3f} | {row.stable_all_years} | {row.stable_both_sides} | {row.gate_robust_feature} |")
    lines.extend([
        "",
        "## Restricciones",
        "",
        "- El piloto está balanceado por etiqueta; AUC es interpretable, prevalencia/WR no.",
        "- Las órdenes existentes antes de los 10 segundos no tienen snapshot completo. Las métricas de vida/supervivencia usan solo órdenes añadidas dentro de la ventana.",
        "- Esta es una puerta de viabilidad discovery, no una validación final ni autorización para modificar entradas.",
        "- Todas las filas con `ts_event` posterior al cutoff fueron excluidas.",
        "",
        f"Artefactos: `{output}`",
    ])
    (output / "final_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(project: Path, mbo_dir: Path, output: Path) -> dict[str, object]:
    manifest_path = project / "contexto_features_atas" / "DATABENTO_MBO_PILOTO_VIABILIDAD_30_AB_20260720.csv"
    mbp_path = project / "outputs" / "preentry_liquidity_features_20260720_preentry_r2" / "preentry_mbp_feature_ledger.csv"
    engineered_path = project / "outputs" / "absorption_breakout_research_20260720_085139" / "engineered_features.csv"
    manifest = pd.read_csv(manifest_path)
    mbp = pd.read_csv(mbp_path)
    engineered = pd.read_csv(engineered_path)
    output.mkdir(parents=True, exist_ok=False)

    mbo_ledger = extract_ledger(manifest, mbp, mbo_dir)
    frame = join_existing_features(mbo_ledger, mbp, engineered)
    metrics, predictions, sets = evaluate_feature_sets(frame)
    permutation_summary, permutation_distribution = permutation_test(frame, sets, metrics)
    univariate = univariate_stability(frame)
    gate, gate_passed = apply_gate(metrics, permutation_summary, univariate)
    plots = create_plots(output, frame, metrics, predictions, univariate)

    mbo_ledger.to_csv(output / "mbo_feature_ledger.csv", index=False)
    frame.to_csv(output / "joined_mbo_mbp_tape_features.csv", index=False)
    metrics.to_csv(output / "loyo_model_metrics.csv", index=False)
    predictions.to_csv(output / "loyo_predictions.csv", index=False)
    permutation_summary.to_csv(output / "permutation_tests.csv", index=False)
    permutation_distribution.to_csv(output / "permutation_distribution.csv", index=False)
    univariate.to_csv(output / "mbo_compact_feature_stability.csv", index=False)
    gate.to_csv(output / "purchase_gate.csv", index=False)
    write_report(output, frame, metrics, permutation_summary, univariate, gate, gate_passed)

    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": len(frame),
        "families": frame["family"].value_counts().sort_index().to_dict(),
        "years": frame["year"].value_counts().sort_index().to_dict(),
        "directions": frame["burst_side"].value_counts().sort_index().to_dict(),
        "causal_rows": int(frame["mbo_causal_rows"].sum()),
        "post_cutoff_rows_excluded": int(frame["mbo_post_cutoff_rows_excluded"].sum()),
        "all_causal_max_ok": bool(frame["mbo_causal_max_ok"].eq(1).all()),
        "permutations": PERMUTATIONS,
        "gate_passed": gate_passed,
        "additional_purchase_authorized_by_gate": gate_passed,
        "validation_dates_opened": 0,
        "atas_replay_launched": False,
        "plots": plots,
        "output": str(output),
    }
    (output / "run_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument(
        "--mbo-dir",
        type=Path,
        default=Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\databento_mbo\liquidity_burst_pilot_20260720"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.project, args.mbo_dir, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
