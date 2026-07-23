"""Pattern mining and classification for causal post-LB DOM+tape sequences.

The predictor path is strictly bounded by:

    t_burst <= event causal timestamp <= t_decision

Outcomes are joined only after all sequence features have been constructed.
The module deliberately keeps the primary experiment small: physical 100 ms
states, transition paths, short subsequences, temporal validation, permutation
tests, and an explicit abstention policy.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import absorption_breakout_research as labels


EXPECTED_VERSION = "liquidity-burst-detector-2026-07-22-v7-postburst-matrix"
LEGACY_VERSION = "liquidity-burst-detector-2026-07-21-v6-causal-sequence"
RANDOM_SEED = 20260722
BIN_MILLISECONDS = 100
EXECUTION_LATENCY_MILLISECONDS = 100.0
ABSTENTION_CONFIDENCE = 0.65
PRIMARY_FEATURE_FAMILY = "transitions_sequences"
PRIMARY_MODEL = "logistic"
MODEL_FAMILIES = (labels.FAMILY_ABSORPTION, labels.FAMILY_CONTINUATION)

STATE_DICTIONARY = {
    "LB": "Inicio causal del Liquidity Burst.",
    "EFF": "Agresión alineada con avance eficiente del precio.",
    "STALL": "Agresión alineada sin avance proporcional.",
    "CF": "Tape contrario domina el bin causal.",
    "WD": "Liquidez delante disminuye sin ejecución alineada simultánea observable.",
    "CON": "Liquidez delante disminuye junto con ejecución alineada observable.",
    "REF": "Liquidez delante aumenta tras el burst.",
    "REFP": "Reposición delante repetida en el mismo nivel dentro de 500 ms.",
    "BDP": "Disminución de liquidez detrás del movimiento.",
    "BRF": "Reposición de liquidez detrás del movimiento.",
}

BASELINE_FEATURES = [
    "Delta1s",
    "Velocity1s",
    "ContractsPerSecond",
    "DOM_Directional_Microprice_Ticks",
    "DOM_Directional_Depth_Imbalance_L1",
    "DOM_Directional_Depth_Imbalance_L3",
    "DOM_Directional_PullStack_1s",
    "DOM_Near_Churn_Per_Aggressive_1s",
]

TIMELINE_COLUMNS = [
    "Detector_VERSION", "BurstId", "Burst_Side", "Burst_Timestamp_UTC",
    "Decision_Timestamp_UTC", "Event_Sequence_In_Burst", "Global_Arrival_Sequence",
    "Event_Causal_Timestamp_UTC", "Event_Available_Timestamp_UTC",
    "Offset_To_Decision_Milliseconds", "Event_Type", "Event_State", "Ahead_Behind",
    "Trade_Alignment", "Price", "Directional_Price_From_Burst_Ticks", "Depth_Delta",
    "Trade_Volume", "Directional_Microprice_Ticks",
    "Directional_Depth_Imbalance_L1", "Book_Snapshot_Valid",
    "Available_Before_Decision", "Causal_Flag", "Model_Eligibility",
]


def _numeric(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")


def _boolean(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").eq(1)
    textual = series.astype(str).str.strip().str.lower().isin({"true", "yes", "si", "1", "1.0"})
    return numeric | textual


def load_timeline(results_folder: Path | str) -> pd.DataFrame:
    path = Path(results_folder) / "burst_causal_timeline.csv"
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    header = pd.read_csv(path, nrows=0).columns
    usecols = [column for column in TIMELINE_COLUMNS if column in header]
    frame = pd.read_csv(path, usecols=usecols, low_memory=False)
    for column in (
        "Burst_Timestamp_UTC", "Decision_Timestamp_UTC",
        "Event_Causal_Timestamp_UTC", "Event_Available_Timestamp_UTC",
    ):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    _numeric(frame, [
        "Event_Sequence_In_Burst", "Global_Arrival_Sequence",
        "Offset_To_Decision_Milliseconds", "Price",
        "Directional_Price_From_Burst_Ticks", "Depth_Delta", "Trade_Volume",
        "Directional_Microprice_Ticks", "Directional_Depth_Imbalance_L1",
        "Book_Snapshot_Valid",
    ])
    if {"BurstId", "Event_Sequence_In_Burst"}.issubset(frame.columns):
        frame = frame.drop_duplicates(["BurstId", "Event_Sequence_In_Burst"], keep="last")
    return frame


def filter_postburst(timeline: pd.DataFrame) -> pd.DataFrame:
    if timeline.empty:
        return timeline.copy()
    mask = (
        timeline["Event_Causal_Timestamp_UTC"].ge(timeline["Burst_Timestamp_UTC"])
        & timeline["Event_Causal_Timestamp_UTC"].le(timeline["Decision_Timestamp_UTC"])
    )
    return timeline.loc[mask].sort_values(
        ["Burst_Timestamp_UTC", "Global_Arrival_Sequence"], kind="stable"
    ).reset_index(drop=True)


def audit_timeline(
    timeline: pd.DataFrame,
    *,
    allow_legacy: bool = False,
) -> tuple[pd.DataFrame, bool, pd.DataFrame]:
    rows: list[dict[str, object]] = []

    def add(check: str, evidence: object, passed: bool, required: bool = True) -> None:
        rows.append({"check": check, "evidence": evidence, "passed": bool(passed), "required": required})

    required = set(TIMELINE_COLUMNS)
    add("TIMELINE_PRESENT", f"rows={len(timeline)}", not timeline.empty)
    add("SCHEMA", f"required={len(required)}", required.issubset(timeline.columns))
    if timeline.empty or not required.issubset(timeline.columns):
        audit = pd.DataFrame(rows)
        return audit, False, pd.DataFrame()

    versions = sorted(timeline["Detector_VERSION"].dropna().astype(str).unique().tolist())
    accepted = {EXPECTED_VERSION, LEGACY_VERSION} if allow_legacy else {EXPECTED_VERSION}
    add("VERSION", versions, set(versions).issubset(accepted) and bool(versions))
    post = filter_postburst(timeline)
    pre_count = int((timeline["Event_Causal_Timestamp_UTC"] < timeline["Burst_Timestamp_UTC"]).sum())
    post_decision = int((timeline["Event_Causal_Timestamp_UTC"] > timeline["Decision_Timestamp_UTC"]).sum())
    add("SOURCE_POSTBURST_ONLY", f"pre_burst_rows={pre_count}", pre_count == 0, required=not allow_legacy)
    add("NO_POST_DECISION", f"violations={post_decision}", post_decision == 0)
    add("ANALYSIS_POSTBURST_FILTER", f"eligible={len(post)}/{len(timeline)}", not post.empty)
    add(
        "AVAILABLE_FLAG",
        f"true={int(_boolean(post['Available_Before_Decision']).sum())}/{len(post)}",
        bool(_boolean(post["Available_Before_Decision"]).all()),
    )
    add(
        "CAUSAL_FLAG",
        f"true={int(_boolean(post['Causal_Flag']).sum())}/{len(post)}",
        bool(_boolean(post["Causal_Flag"]).all()),
    )
    add(
        "MODEL_ELIGIBILITY",
        f"eligible={int(post['Model_Eligibility'].astype(str).eq('CAUSAL_PRE_DECISION').sum())}/{len(post)}",
        bool(post["Model_Eligibility"].astype(str).eq("CAUSAL_PRE_DECISION").all()),
    )
    unique = not post.duplicated(["BurstId", "Event_Sequence_In_Burst"]).any()
    add("UNIQUE_BURST_SEQUENCE", "BurstId+sequence unique", unique)
    arrival_ok = True
    causal_clock_ok = True
    for _, group in post.groupby("BurstId", sort=False):
        ordered = group.sort_values("Event_Sequence_In_Burst")
        arrival_ok &= bool(ordered["Global_Arrival_Sequence"].is_monotonic_increasing)
        causal_clock_ok &= bool(ordered["Event_Causal_Timestamp_UTC"].is_monotonic_increasing)
    add("ARRIVAL_ORDER_STRICT", "arrival monotonic within burst", arrival_ok)
    add("CAUSAL_CLOCK_MONOTONIC", "causal clock monotonic within burst", causal_clock_ok)
    types = set(post["Event_Type"].dropna().astype(str))
    dom_and_tape = any(value.startswith("DEPTH_") for value in types) and any(value.startswith("TAPE_") for value in types)
    add("DOM_AND_TAPE", sorted(types), dom_and_tape)
    per_burst = post.groupby("BurstId").size()
    add("POSTBURST_EVENT_DENSITY", f"median={float(per_burst.median()) if len(per_burst) else 0:.1f}", len(per_burst) >= 1 and per_burst.median() >= 25)
    audit = pd.DataFrame(rows)
    required_rows = audit["required"].astype(bool)
    passed = bool(audit.loc[required_rows, "passed"].all())
    return audit, passed, post


def technical_gate(results_folder: Path | str) -> tuple[pd.DataFrame, bool]:
    timeline = load_timeline(results_folder)
    audit, passed, post = audit_timeline(timeline, allow_legacy=False)
    extra = pd.DataFrame([
        {
            "check": "TECHNICAL_BURSTS",
            "evidence": f"bursts={post['BurstId'].nunique() if not post.empty else 0} expected>=2",
            "passed": bool(not post.empty and post["BurstId"].nunique() >= 2),
            "required": True,
        }
    ])
    audit = pd.concat([audit, extra], ignore_index=True)
    return audit, bool(passed and extra["passed"].all())


def _dominant_state(group: pd.DataFrame, recent_refills: dict[float, int], bin_index: int) -> tuple[str, dict[str, float]]:
    event_type = group["Event_Type"].astype(str)
    tape = event_type.str.startswith("TAPE_")
    dom = event_type.str.startswith("DEPTH_")
    aligned = tape & group["Trade_Alignment"].astype(str).eq("ALIGNED")
    counter = tape & group["Trade_Alignment"].astype(str).eq("COUNTER")
    volume = pd.to_numeric(group["Trade_Volume"], errors="coerce").fillna(0.0).abs()
    depth = pd.to_numeric(group["Depth_Delta"], errors="coerce").fillna(0.0)
    state = group["Event_State"].astype(str)
    ahead = dom & group["Ahead_Behind"].astype(str).eq("AHEAD")
    behind = dom & group["Ahead_Behind"].astype(str).eq("BEHIND")

    aligned_volume = float(volume[aligned].sum())
    counter_volume = float(volume[counter].sum())
    progress_volume = float(volume[aligned & state.eq("AGGRESSION_PROGRESS")].sum())
    stall_volume = float(volume[aligned & state.eq("AGGRESSION_STALL")].sum())
    ahead_add = float(depth[ahead & depth.gt(0)].sum())
    ahead_remove = float((-depth[ahead & depth.lt(0)]).sum())
    behind_add = float(depth[behind & depth.gt(0)].sum())
    behind_remove = float((-depth[behind & depth.lt(0)]).sum())

    flow = ""
    if counter_volume > aligned_volume and counter_volume > 0:
        flow = "CF"
    elif progress_volume > stall_volume and progress_volume > 0:
        flow = "EFF"
    elif aligned_volume > 0:
        flow = "STALL"
    elif counter_volume > 0:
        flow = "CF"

    book = ""
    magnitudes = {
        "ahead_remove": ahead_remove,
        "ahead_add": ahead_add,
        "behind_remove": behind_remove,
        "behind_add": behind_add,
    }
    dominant = max(magnitudes, key=magnitudes.get)
    if magnitudes[dominant] > 0:
        if dominant == "ahead_remove":
            book = "CON" if aligned_volume > 0 else "WD"
        elif dominant == "ahead_add":
            refill_rows = group.loc[ahead & depth.gt(0)]
            refill_price = pd.to_numeric(refill_rows["Price"], errors="coerce").dropna()
            repeated = False
            if not refill_price.empty:
                price = float(refill_price.mode().iloc[0])
                repeated = price in recent_refills and bin_index - recent_refills[price] <= 5
                recent_refills[price] = bin_index
            book = "REFP" if repeated else "REF"
        elif dominant == "behind_remove":
            book = "BDP"
        else:
            book = "BRF"

    token = "+".join(value for value in (flow, book) if value) or "QUIET"
    metrics = {
        "aligned_trade_volume": aligned_volume,
        "counter_trade_volume": counter_volume,
        "ahead_add_volume": ahead_add,
        "ahead_remove_volume": ahead_remove,
        "behind_add_volume": behind_add,
        "behind_remove_volume": behind_remove,
        "event_count": float(len(group)),
    }
    return token, metrics


def build_macro_states(postburst: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    state_rows: list[dict[str, object]] = []
    sequence_rows: list[dict[str, object]] = []
    if postburst.empty:
        return pd.DataFrame(), pd.DataFrame()

    for burst_id, raw in postburst.groupby("BurstId", sort=False):
        raw = raw.sort_values(["Event_Causal_Timestamp_UTC", "Global_Arrival_Sequence"], kind="stable").copy()
        burst_time = raw["Burst_Timestamp_UTC"].iloc[0]
        decision_time = raw["Decision_Timestamp_UTC"].iloc[0]
        raw["bin_index"] = np.floor(
            (raw["Event_Causal_Timestamp_UTC"] - burst_time).dt.total_seconds() * 1000.0 / BIN_MILLISECONDS
        ).astype(int)
        recent_refills: dict[float, int] = {}
        burst_states: list[dict[str, object]] = []
        for bin_index, group in raw.groupby("bin_index", sort=True):
            token, metrics = _dominant_state(group, recent_refills, int(bin_index))
            if token == "QUIET":
                continue
            state_time = group["Event_Causal_Timestamp_UTC"].max()
            price_values = pd.to_numeric(group["Directional_Price_From_Burst_Ticks"], errors="coerce").dropna()
            micro_values = pd.to_numeric(group["Directional_Microprice_Ticks"], errors="coerce").dropna()
            imbalance_values = pd.to_numeric(group["Directional_Depth_Imbalance_L1"], errors="coerce").dropna()
            row = {
                "BurstId": burst_id,
                "BurstSide": raw["Burst_Side"].iloc[0],
                "Burst_Timestamp_UTC": burst_time,
                "Decision_Timestamp_UTC": decision_time,
                "bin_index": int(bin_index),
                "state": token,
                "state_start_utc": group["Event_Causal_Timestamp_UTC"].min(),
                "state_completion_utc": state_time,
                "lead_time_ms": float((decision_time - state_time).total_seconds() * 1000.0),
                "directional_price_ticks": float(price_values.iloc[-1]) if not price_values.empty else np.nan,
                "directional_microprice_ticks": float(micro_values.iloc[-1]) if not micro_values.empty else np.nan,
                "directional_imbalance_l1": float(imbalance_values.iloc[-1]) if not imbalance_values.empty else np.nan,
                **metrics,
            }
            if burst_states and burst_states[-1]["state"] == token:
                previous = burst_states[-1]
                previous["state_completion_utc"] = row["state_completion_utc"]
                previous["lead_time_ms"] = row["lead_time_ms"]
                previous["directional_price_ticks"] = row["directional_price_ticks"]
                previous["directional_microprice_ticks"] = row["directional_microprice_ticks"]
                previous["directional_imbalance_l1"] = row["directional_imbalance_l1"]
                for name in (
                    "aligned_trade_volume", "counter_trade_volume", "ahead_add_volume",
                    "ahead_remove_volume", "behind_add_volume", "behind_remove_volume", "event_count",
                ):
                    previous[name] = float(previous[name]) + float(row[name])
            else:
                burst_states.append(row)

        for index, row in enumerate(burst_states, start=1):
            row["state_index"] = index
            row["state_duration_ms"] = float(
                (row["state_completion_utc"] - row["state_start_utc"]).total_seconds() * 1000.0
            )
            state_rows.append(row)
        tokens = ["LB", *[str(row["state"]) for row in burst_states]]
        sequence_rows.append({
            "BurstId": burst_id,
            "BurstSide": raw["Burst_Side"].iloc[0],
            "Burst_Timestamp_UTC": burst_time,
            "Decision_Timestamp_UTC": decision_time,
            "macro_state_count": len(burst_states),
            "postburst_event_count": len(raw),
            "postburst_duration_ms": float((decision_time - burst_time).total_seconds() * 1000.0),
            "sequence": ">".join(tokens),
        })
    return pd.DataFrame(state_rows), pd.DataFrame(sequence_rows)


def _asof_price(raw: pd.DataFrame, timestamp: pd.Timestamp) -> float:
    eligible = raw.loc[raw["Event_Causal_Timestamp_UTC"].le(timestamp)]
    if eligible.empty:
        return np.nan
    values = pd.to_numeric(eligible["Directional_Price_From_Burst_Ticks"], errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else np.nan


def build_transition_events(postburst: pd.DataFrame, states: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if states.empty:
        return pd.DataFrame()
    raw_groups = {key: value.sort_values("Event_Causal_Timestamp_UTC") for key, value in postburst.groupby("BurstId")}
    for burst_id, frame in states.groupby("BurstId", sort=False):
        frame = frame.sort_values("state_index").copy()
        raw = raw_groups[burst_id]
        burst_time = frame["Burst_Timestamp_UTC"].iloc[0]
        decision_time = frame["Decision_Timestamp_UTC"].iloc[0]
        previous_state = "LB"
        previous_time = burst_time
        previous_duration = 0.0
        for item in frame.itertuples(index=False):
            completion = item.state_completion_utc
            row = {
                "BurstId": burst_id,
                "BurstSide": item.BurstSide,
                "from_state": previous_state,
                "to_state": item.state,
                "transition": f"{previous_state}>{item.state}",
                "transition_time_ms": float((completion - previous_time).total_seconds() * 1000.0),
                "origin_duration_ms": previous_duration,
                "destination_duration_ms": float(item.state_duration_ms),
                "completion_timestamp_utc": completion,
                "lead_time_ms": float((decision_time - completion).total_seconds() * 1000.0),
                "exploitable_lead_time_ms": float((decision_time - completion).total_seconds() * 1000.0 - EXECUTION_LATENCY_MILLISECONDS),
                "aligned_trade_volume": float(item.aligned_trade_volume),
                "counter_trade_volume": float(item.counter_trade_volume),
                "ahead_add_volume": float(item.ahead_add_volume),
                "ahead_remove_volume": float(item.ahead_remove_volume),
                "event_count": float(item.event_count),
            }
            price_at_completion = _asof_price(raw, completion)
            for horizon in (100, 250, 500):
                target = completion + pd.Timedelta(milliseconds=horizon)
                row[f"price_response_{horizon}ms"] = (
                    _asof_price(raw, target) - price_at_completion
                    if target <= decision_time and math.isfinite(price_at_completion)
                    else np.nan
                )
            rows.append(row)
            previous_state = str(item.state)
            previous_time = completion
            previous_duration = float(item.state_duration_ms)
    return pd.DataFrame(rows)


def join_labels(results_folder: Path | str, sequences: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    outcome, audit = labels.build_dataset(Path(results_folder))
    if outcome.empty or sequences.empty:
        return pd.DataFrame(), audit
    identity = [
        column for column in (
            "BurstId", "fecha", "family", "family_reason", "split", "BurstSide",
            "ExecutionSide", "Result_Label", "MAE_ticks", "MFE_ticks",
        ) if column in outcome
    ]
    clean_outcome = outcome.loc[outcome["family"].isin(labels.ANALYSIS_FAMILIES), identity]
    clean_outcome = clean_outcome.drop_duplicates("BurstId", keep="last")
    return sequences.merge(clean_outcome, on="BurstId", how="inner", suffixes=("", "_outcome"), validate="one_to_one"), audit


def _transition_statistics(transitions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if transitions.empty:
        return pd.DataFrame()
    for family, family_frame in transitions.groupby("family"):
        origin_counts = family_frame.groupby("from_state").size()
        family_bursts = max(1, family_frame["BurstId"].nunique())
        for (origin, destination), group in family_frame.groupby(["from_state", "to_state"]):
            rows.append({
                "family": family,
                "from_state": origin,
                "to_state": destination,
                "transition": f"{origin}>{destination}",
                "count": len(group),
                "eligible_origin_count": int(origin_counts.get(origin, 0)),
                "probability": len(group) / max(1, int(origin_counts.get(origin, 0))),
                "support_bursts": group["BurstId"].nunique(),
                "burst_coverage": group["BurstId"].nunique() / family_bursts,
                "median_transition_time_ms": group["transition_time_ms"].median(),
                "p25_transition_time_ms": group["transition_time_ms"].quantile(0.25),
                "p75_transition_time_ms": group["transition_time_ms"].quantile(0.75),
                "median_origin_duration_ms": group["origin_duration_ms"].median(),
                "median_destination_duration_ms": group["destination_duration_ms"].median(),
                "median_aligned_trade_volume": group["aligned_trade_volume"].median(),
                "median_counter_trade_volume": group["counter_trade_volume"].median(),
                "median_ahead_add_volume": group["ahead_add_volume"].median(),
                "median_ahead_remove_volume": group["ahead_remove_volume"].median(),
                "median_lead_time_ms": group["lead_time_ms"].median(),
                "median_exploitable_lead_time_ms": group["exploitable_lead_time_ms"].median(),
                "price_response_100ms": group["price_response_100ms"].median(),
                "price_response_250ms": group["price_response_250ms"].median(),
                "price_response_500ms": group["price_response_500ms"].median(),
            })
    return pd.DataFrame(rows)


def _pivot_transition(stats_frame: pd.DataFrame, family: str, value: str) -> pd.DataFrame:
    frame = stats_frame.loc[stats_frame["family"].eq(family)]
    if frame.empty:
        return pd.DataFrame()
    return frame.pivot(index="from_state", columns="to_state", values=value).fillna(0.0)


def _pattern_occurrences(states: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for burst_id, group in states.groupby("BurstId", sort=False):
        group = group.sort_values("state_index")
        tokens = ["LB", *group["state"].astype(str).tolist()]
        times = [group["Burst_Timestamp_UTC"].iloc[0], *group["state_completion_utc"].tolist()]
        decision = group["Decision_Timestamp_UTC"].iloc[0]
        seen: set[str] = set()
        for length in (2, 3, 4):
            for start in range(0, len(tokens) - length + 1):
                pattern = ">".join(tokens[start:start + length])
                if pattern in seen:
                    continue
                seen.add(pattern)
                completion = times[start + length - 1]
                rows.append({
                    "BurstId": burst_id,
                    "pattern": pattern,
                    "length": length,
                    "completion_timestamp_utc": completion,
                    "lead_time_ms": float((decision - completion).total_seconds() * 1000.0),
                    "exploitable_lead_time_ms": float((decision - completion).total_seconds() * 1000.0 - EXECUTION_LATENCY_MILLISECONDS),
                })
    return pd.DataFrame(rows)


def _pattern_matrix(occurrences: pd.DataFrame, labeled: pd.DataFrame) -> pd.DataFrame:
    if occurrences.empty or labeled.empty:
        return pd.DataFrame()
    joined = occurrences.merge(labeled[["BurstId", "family", "split", "BurstSide", "fecha"]], on="BurstId", how="inner")
    clean = labeled.loc[labeled["family"].isin(MODEL_FAMILIES)]
    class_counts = clean["family"].value_counts().to_dict()
    prior_a = class_counts.get(labels.FAMILY_ABSORPTION, 0) / max(1, len(clean))
    rows: list[dict[str, object]] = []
    for pattern, group in joined.groupby("pattern"):
        a = group.loc[group["family"].eq(labels.FAMILY_ABSORPTION), "BurstId"].nunique()
        b = group.loc[group["family"].eq(labels.FAMILY_CONTINUATION), "BurstId"].nunique()
        support_a = a / max(1, class_counts.get(labels.FAMILY_ABSORPTION, 0))
        support_b = b / max(1, class_counts.get(labels.FAMILY_CONTINUATION, 0))
        table = [
            [a, max(0, class_counts.get(labels.FAMILY_ABSORPTION, 0) - a)],
            [b, max(0, class_counts.get(labels.FAMILY_CONTINUATION, 0) - b)],
        ]
        _, fisher_p = stats.fisher_exact(table) if a + b else (np.nan, np.nan)
        rows.append({
            "pattern": pattern,
            "length": int(group["length"].iloc[0]),
            "support_bursts": group["BurstId"].nunique(),
            "support_A": support_a,
            "support_B": support_b,
            "delta_support_A_minus_B": support_a - support_b,
            "confidence_A": a / max(1, a + b),
            "confidence_B": b / max(1, a + b),
            "lift_A": (a / max(1, a + b)) / max(prior_a, 1e-12),
            "median_lead_time_ms": group["lead_time_ms"].median(),
            "median_exploitable_lead_time_ms": group["exploitable_lead_time_ms"].median(),
            "fisher_p_value": fisher_p,
        })
    return pd.DataFrame(rows).sort_values(["support_bursts", "pattern"], ascending=[False, True])


def _bifurcation_matrix(states: pd.DataFrame, labeled: pd.DataFrame) -> pd.DataFrame:
    label_map = labeled.set_index("BurstId")["family"].to_dict() if not labeled.empty else {}
    rows: list[dict[str, object]] = []
    branch_records: list[dict[str, object]] = []
    for burst_id, group in states.groupby("BurstId", sort=False):
        family = label_map.get(burst_id)
        if family not in MODEL_FAMILIES:
            continue
        group = group.sort_values("state_index")
        tokens = ["LB", *group["state"].astype(str).tolist()]
        times = [group["Burst_Timestamp_UTC"].iloc[0], *group["state_completion_utc"].tolist()]
        decision = group["Decision_Timestamp_UTC"].iloc[0]
        for history_length in (1, 2):
            for index in range(history_length, len(tokens)):
                history = ">".join(tokens[index-history_length:index])
                branch_records.append({
                    "BurstId": burst_id,
                    "family": family,
                    "history": history,
                    "next_state": tokens[index],
                    "lead_time_ms": float((decision - times[index]).total_seconds() * 1000.0),
                })
    branch = pd.DataFrame(branch_records)
    if branch.empty:
        return branch
    for (history, next_state), group in branch.groupby(["history", "next_state"]):
        support = group["BurstId"].nunique()
        a = group.loc[group["family"].eq(labels.FAMILY_ABSORPTION), "BurstId"].nunique()
        b = group.loc[group["family"].eq(labels.FAMILY_CONTINUATION), "BurstId"].nunique()
        history_group = branch.loc[branch["history"].eq(history)]
        history_a = history_group.loc[history_group["family"].eq(labels.FAMILY_ABSORPTION), "BurstId"].nunique()
        history_b = history_group.loc[history_group["family"].eq(labels.FAMILY_CONTINUATION), "BurstId"].nunique()
        rows.append({
            "history": history,
            "next_state": next_state,
            "support_bursts": support,
            "P_A_given_branch": a / max(1, a + b),
            "P_B_given_branch": b / max(1, a + b),
            "delta_probability_A_minus_B": a / max(1, history_a) - b / max(1, history_b),
            "median_lead_time_ms": group["lead_time_ms"].median(),
        })
    return pd.DataFrame(rows).sort_values(["support_bursts", "history"], ascending=[False, True])


def _pattern_stability(occurrences: pd.DataFrame, labeled: pd.DataFrame) -> pd.DataFrame:
    if occurrences.empty or labeled.empty:
        return pd.DataFrame()
    presence = occurrences[["BurstId", "pattern"]].drop_duplicates().assign(present=1)
    clean = labeled.loc[labeled["family"].isin(MODEL_FAMILIES), ["BurstId", "family", "split", "BurstSide", "fecha"]]
    patterns = presence["pattern"].value_counts().head(100).index.tolist()
    rows: list[dict[str, object]] = []
    for pattern in patterns:
        ids = set(presence.loc[presence["pattern"].eq(pattern), "BurstId"])
        row: dict[str, object] = {"pattern": pattern}
        signs: list[int] = []
        for split in ("discovery", "validation", "holdout"):
            frame = clean.loc[clean["split"].eq(split)]
            a = frame.loc[frame["family"].eq(labels.FAMILY_ABSORPTION)]
            b = frame.loc[frame["family"].eq(labels.FAMILY_CONTINUATION)]
            rate_a = a["BurstId"].isin(ids).mean() if len(a) else np.nan
            rate_b = b["BurstId"].isin(ids).mean() if len(b) else np.nan
            delta = rate_a - rate_b if pd.notna(rate_a) and pd.notna(rate_b) else np.nan
            row[f"support_{split}"] = int(frame["BurstId"].isin(ids).sum())
            row[f"delta_{split}_A_minus_B"] = delta
            if split in {"discovery", "validation"} and pd.notna(delta) and delta != 0:
                signs.append(int(np.sign(delta)))
        for side in ("BUY", "SELL"):
            frame = clean.loc[clean["BurstSide"].eq(side)]
            a = frame.loc[frame["family"].eq(labels.FAMILY_ABSORPTION)]
            b = frame.loc[frame["family"].eq(labels.FAMILY_CONTINUATION)]
            rate_a = a["BurstId"].isin(ids).mean() if len(a) else np.nan
            rate_b = b["BurstId"].isin(ids).mean() if len(b) else np.nan
            row[f"delta_{side}_A_minus_B"] = rate_a - rate_b if pd.notna(rate_a) and pd.notna(rate_b) else np.nan
        row["discovery_validation_sign_stable"] = int(len(signs) == 2 and signs[0] == signs[1])
        rows.append(row)
    return pd.DataFrame(rows)


def _final_selection(patterns: pd.DataFrame, stability: pd.DataFrame) -> pd.DataFrame:
    if patterns.empty:
        return pd.DataFrame()
    merged = patterns.merge(stability, on="pattern", how="left")
    statuses = []
    for row in merged.itertuples(index=False):
        raw_support_discovery = getattr(row, "support_discovery", 0)
        raw_support_validation = getattr(row, "support_validation", 0)
        support_discovery = int(raw_support_discovery) if pd.notna(raw_support_discovery) else 0
        support_validation = int(raw_support_validation) if pd.notna(raw_support_validation) else 0
        delta_discovery = getattr(row, "delta_discovery_A_minus_B", np.nan)
        stable = bool(getattr(row, "discovery_validation_sign_stable", 0))
        if support_discovery < 3 or support_validation < 2:
            status = "LOW_COVERAGE"
        elif not stable:
            status = "UNSTABLE"
        elif pd.notna(delta_discovery) and abs(float(delta_discovery)) >= 0.20:
            status = "PROMISING"
        else:
            status = "WEAK"
        statuses.append(status)
    merged["final_status"] = statuses
    return merged.sort_values(
        ["final_status", "support_bursts", "median_exploitable_lead_time_ms"],
        ascending=[True, False, False],
    )


def _feature_tables(
    results_folder: Path,
    labeled: pd.DataFrame,
    transitions: pd.DataFrame,
    occurrences: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    base = labeled.copy()
    burst_path = results_folder / "burst_events.csv"
    if burst_path.exists():
        header = pd.read_csv(burst_path, nrows=0).columns
        usecols = [column for column in ["BurstId", *BASELINE_FEATURES] if column in header]
        burst = pd.read_csv(burst_path, usecols=usecols, low_memory=False).drop_duplicates("BurstId", keep="last")
        base = base.merge(burst, on="BurstId", how="left")

    discovery_ids = set(base.loc[base["split"].eq("discovery"), "BurstId"])
    transition_presence = transitions[["BurstId", "transition"]].drop_duplicates()
    ranked_transitions = (
        transition_presence.loc[transition_presence["BurstId"].isin(discovery_ids), "transition"]
        .value_counts()
    )
    selected_transitions = ranked_transitions.loc[ranked_transitions.ge(3)].head(6).index.tolist()
    for pattern in selected_transitions:
        ids = set(transition_presence.loc[transition_presence["transition"].eq(pattern), "BurstId"])
        base[f"tr__{pattern}"] = base["BurstId"].isin(ids).astype(int)

    sequence_presence = occurrences[["BurstId", "pattern"]].drop_duplicates()
    eligible_occurrences = sequence_presence.loc[
        sequence_presence["BurstId"].isin(discovery_ids)
        & sequence_presence["pattern"].str.count(">").between(2, 3)
    ]
    ranked_sequences = eligible_occurrences["pattern"].value_counts()
    selected_sequences = ranked_sequences.loc[ranked_sequences.ge(3)].head(6).index.tolist()
    for pattern in selected_sequences:
        ids = set(sequence_presence.loc[sequence_presence["pattern"].eq(pattern), "BurstId"])
        base[f"sq__{pattern}"] = base["BurstId"].isin(ids).astype(int)

    baseline = [column for column in BASELINE_FEATURES if column in base][:6]
    transition_features = [f"tr__{value}" for value in selected_transitions]
    sequence_features = [f"sq__{value}" for value in selected_sequences]
    feature_sets = {
        "snapshots": baseline,
        "transitions": transition_features,
        "sequences": sequence_features,
        "transitions_sequences": transition_features[:4] + sequence_features[:4],
        "all_combined": baseline[:4] + transition_features[:3] + sequence_features[:3],
    }
    return base, feature_sets


def _bootstrap_balanced_accuracy(y: np.ndarray, pred: np.ndarray, repeats: int = 1000) -> tuple[float, float]:
    rng = np.random.default_rng(RANDOM_SEED)
    classes = np.unique(y)
    if len(classes) < 2:
        return np.nan, np.nan
    by_class = [np.flatnonzero(y == value) for value in classes]
    values = []
    for _ in range(repeats):
        indices = np.concatenate([rng.choice(index, len(index), replace=True) for index in by_class])
        values.append(balanced_accuracy_score(y[indices], pred[indices]))
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def _classification_metrics(y: np.ndarray, pred: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    target = (y == labels.FAMILY_ABSORPTION).astype(int)
    predicted_target = (pred == labels.FAMILY_ABSORPTION).astype(int)
    matrix = confusion_matrix(target, predicted_target, labels=[1, 0])
    tp, fn = matrix[0, 0], matrix[0, 1]
    fp, tn = matrix[1, 0], matrix[1, 1]
    ci_low, ci_high = _bootstrap_balanced_accuracy(y, pred)
    return {
        "n": len(y),
        "n_A": int(target.sum()),
        "n_B": int((1 - target).sum()),
        "sensitivity_A": tp / max(1, tp + fn),
        "specificity_B": tn / max(1, tn + fp),
        "precision_A": precision_score(target, predicted_target, zero_division=0),
        "precision_B": precision_score(1 - target, 1 - predicted_target, zero_division=0),
        "balanced_accuracy": balanced_accuracy_score(y, pred) if len(np.unique(y)) > 1 else np.nan,
        "balanced_accuracy_ci_low": ci_low,
        "balanced_accuracy_ci_high": ci_high,
        "roc_auc_A_vs_B": roc_auc_score(target, probability) if len(np.unique(target)) > 1 else np.nan,
        "pr_auc_A": average_precision_score(target, probability) if target.sum() else np.nan,
        "f1_A": f1_score(target, predicted_target, zero_division=0),
        "f1_B": f1_score(1 - target, 1 - predicted_target, zero_division=0),
        "mcc": matthews_corrcoef(target, predicted_target) if len(np.unique(predicted_target)) > 1 else 0.0,
        "accuracy": accuracy_score(target, predicted_target),
        "brier": brier_score_loss(target, probability),
        "TP_A": int(tp), "FN_A": int(fn), "FP_A": int(fp), "TN_A": int(tn),
    }


def _new_model(name: str):
    if name == "logistic":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(C=0.5, max_iter=3000, class_weight="balanced", random_state=RANDOM_SEED),
        )
    if name == "catboost":
        from catboost import CatBoostClassifier

        return CatBoostClassifier(
            iterations=200, depth=2, learning_rate=0.025, loss_function="Logloss",
            verbose=False, random_seed=RANDOM_SEED, allow_writing_files=False,
        )
    raise ValueError(name)


def _permutation_p_value(
    train_x: np.ndarray,
    train_y: np.ndarray,
    test_x: np.ndarray,
    test_y: np.ndarray,
    observed: float,
    repeats: int = 250,
) -> float:
    if not math.isfinite(observed) or len(np.unique(test_y)) < 2:
        return np.nan
    rng = np.random.default_rng(RANDOM_SEED)
    exceed = 0
    for _ in range(repeats):
        shuffled = rng.permutation(train_y)
        model = _new_model("logistic")
        model.fit(train_x, shuffled)
        pred = np.asarray(model.predict(test_x)).reshape(-1).astype(str)
        score = balanced_accuracy_score(test_y, pred)
        exceed += int(score >= observed - 1e-12)
    return (exceed + 1) / (repeats + 1)


def train_models(dataset: pd.DataFrame, feature_sets: dict[str, list[str]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    metrics_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    clean = dataset.loc[dataset["family"].isin(MODEL_FAMILIES)].copy()
    discovery = clean.loc[clean["split"].eq("discovery")]
    if len(discovery) < 8 or discovery["family"].nunique() < 2:
        return pd.DataFrame([{"status": "INSUFFICIENT_DISCOVERY", "n": len(discovery)}]), pd.DataFrame()

    for feature_family, features in feature_sets.items():
        if not features:
            metrics_rows.append({"feature_family": feature_family, "model": "logistic", "status": "NO_FEATURES"})
            continue
        imputer = SimpleImputer(strategy="median")
        train_x = imputer.fit_transform(discovery[features].apply(pd.to_numeric, errors="coerce"))
        train_y = discovery["family"].astype(str).to_numpy()
        model_names = ["logistic"]
        if feature_family == "all_combined":
            try:
                import catboost  # noqa: F401

                model_names.append("catboost")
            except Exception:
                pass
        for model_name in model_names:
            model = _new_model(model_name)
            model.fit(train_x, train_y)
            for split in ("validation", "holdout"):
                frame = clean.loc[clean["split"].eq(split)].copy()
                if frame.empty:
                    continue
                test_x = imputer.transform(frame[features].apply(pd.to_numeric, errors="coerce"))
                test_y = frame["family"].astype(str).to_numpy()
                pred = np.asarray(model.predict(test_x)).reshape(-1).astype(str)
                classes = np.asarray(model.classes_).astype(str)
                a_index = int(np.flatnonzero(classes == labels.FAMILY_ABSORPTION)[0])
                probability = np.asarray(model.predict_proba(test_x))[:, a_index]
                values = _classification_metrics(test_y, pred, probability)
                permutation_p = (
                    _permutation_p_value(train_x, train_y, test_x, test_y, values["balanced_accuracy"])
                    if model_name == "logistic" and split == "holdout"
                    else np.nan
                )
                metrics_rows.append({
                    "feature_family": feature_family,
                    "model": model_name,
                    "split": split,
                    "status": "OK",
                    "feature_count": len(features),
                    "features": "|".join(features),
                    "permutation_p_value": permutation_p,
                    **values,
                })
                for index, item in enumerate(frame.itertuples(index=False)):
                    prediction_rows.append({
                        "BurstId": item.BurstId,
                        "fecha": item.fecha,
                        "BurstSide": getattr(item, "BurstSide", ""),
                        "family": item.family,
                        "split": split,
                        "feature_family": feature_family,
                        "model": model_name,
                        "probability_A": float(probability[index]),
                        "prediction": pred[index],
                        "confidence": float(max(probability[index], 1.0 - probability[index])),
                        "correct": int(pred[index] == test_y[index]),
                    })
    return pd.DataFrame(metrics_rows), pd.DataFrame(prediction_rows)


def _primary_predictions(predictions: pd.DataFrame, split: str = "holdout") -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame()
    return predictions.loc[
        predictions["feature_family"].eq(PRIMARY_FEATURE_FAMILY)
        & predictions["model"].eq(PRIMARY_MODEL)
        & predictions["split"].eq(split)
    ].copy()


def _confusion_outputs(primary: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if primary.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    order = [labels.FAMILY_ABSORPTION, labels.FAMILY_CONTINUATION]
    matrix = confusion_matrix(primary["family"], primary["prediction"], labels=order)
    absolute = pd.DataFrame(matrix, index=order, columns=order).rename_axis("actual").reset_index()
    normalized_values = matrix / np.maximum(1, matrix.sum(axis=1, keepdims=True))
    normalized = pd.DataFrame(normalized_values, index=order, columns=order).rename_axis("actual").reset_index()
    abstain_prediction = np.where(
        primary["confidence"].ge(ABSTENTION_CONFIDENCE),
        np.where(primary["probability_A"].ge(0.5), "PREDICT_A", "PREDICT_B"),
        "NO_DECISION",
    )
    abstention = pd.crosstab(
        primary["family"],
        pd.Series(abstain_prediction, index=primary.index, name="prediction"),
    ).reindex(index=order, columns=["PREDICT_A", "NO_DECISION", "PREDICT_B"], fill_value=0).reset_index()
    return absolute, normalized, abstention


def _risk_coverage(primary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for threshold in (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80):
        decided = primary.loc[primary["confidence"].ge(threshold)].copy()
        row: dict[str, object] = {
            "confidence_threshold": threshold,
            "coverage": len(decided) / max(1, len(primary)),
            "cases_decided": len(decided),
            "abstention_rate": 1.0 - len(decided) / max(1, len(primary)),
        }
        if not decided.empty:
            row["selective_accuracy"] = decided["correct"].mean()
            if decided["family"].nunique() > 1:
                row["balanced_accuracy"] = balanced_accuracy_score(decided["family"], decided["prediction"])
                target = decided["family"].eq(labels.FAMILY_ABSORPTION).astype(int)
                row["auc"] = roc_auc_score(target, decided["probability_A"])
            else:
                row["balanced_accuracy"] = np.nan
                row["auc"] = np.nan
            row["precision_A"] = precision_score(
                decided["family"].eq(labels.FAMILY_ABSORPTION),
                decided["prediction"].eq(labels.FAMILY_ABSORPTION),
                zero_division=0,
            )
            row["precision_B"] = precision_score(
                decided["family"].eq(labels.FAMILY_CONTINUATION),
                decided["prediction"].eq(labels.FAMILY_CONTINUATION),
                zero_division=0,
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _calibration(primary: pd.DataFrame) -> pd.DataFrame:
    if primary.empty:
        return pd.DataFrame()
    bins = np.linspace(0.0, 1.0, 6)
    frame = primary.copy()
    frame["bin"] = pd.cut(frame["probability_A"], bins=bins, include_lowest=True)
    frame["actual_A"] = frame["family"].eq(labels.FAMILY_ABSORPTION).astype(int)
    rows = []
    for interval, group in frame.groupby("bin", observed=False):
        rows.append({
            "probability_bin": str(interval),
            "n": len(group),
            "mean_probability_A": group["probability_A"].mean() if len(group) else np.nan,
            "observed_frequency_A": group["actual_A"].mean() if len(group) else np.nan,
            "calibration_error": (
                abs(group["probability_A"].mean() - group["actual_A"].mean()) if len(group) else np.nan
            ),
        })
    return pd.DataFrame(rows)


def _classification_slices(primary: pd.DataFrame, column: str) -> pd.DataFrame:
    if primary.empty:
        return pd.DataFrame()
    rows = []
    frame = primary.copy()
    if column == "year":
        frame["year"] = pd.to_datetime(frame["fecha"], errors="coerce").dt.year
    for value, group in frame.groupby(column, dropna=False):
        if group["family"].nunique() < 2:
            rows.append({column: value, "n": len(group), "status": "INSUFFICIENT_CLASS_SUPPORT"})
            continue
        values = _classification_metrics(
            group["family"].astype(str).to_numpy(),
            group["prediction"].astype(str).to_numpy(),
            group["probability_A"].to_numpy(float),
        )
        rows.append({column: value, "status": "OK", **values})
    return pd.DataFrame(rows)


def _error_patterns(primary: pd.DataFrame, occurrences: pd.DataFrame, selection: pd.DataFrame) -> pd.DataFrame:
    if primary.empty:
        return pd.DataFrame()
    pattern_rank = {}
    if not selection.empty:
        ranked = selection.sort_values(["support_bursts", "median_lead_time_ms"], ascending=[False, False])
        pattern_rank = {pattern: index for index, pattern in enumerate(ranked["pattern"].tolist())}
    presence = occurrences[["BurstId", "pattern", "lead_time_ms"]].drop_duplicates(["BurstId", "pattern"])
    rows = []
    for item in primary.itertuples(index=False):
        if item.family == labels.FAMILY_ABSORPTION and item.prediction == labels.FAMILY_ABSORPTION:
            outcome = "TP_A"
        elif item.family == labels.FAMILY_ABSORPTION:
            outcome = "FN_A"
        elif item.prediction == labels.FAMILY_ABSORPTION:
            outcome = "FP_A"
        else:
            outcome = "TN_A"
        burst_patterns = presence.loc[presence["BurstId"].eq(item.BurstId)].copy()
        if not burst_patterns.empty:
            burst_patterns["rank"] = burst_patterns["pattern"].map(pattern_rank).fillna(10_000)
            dominant = burst_patterns.sort_values(["rank", "lead_time_ms"], ascending=[True, False]).iloc[0]
            pattern = dominant["pattern"]
            lead = dominant["lead_time_ms"]
        else:
            pattern, lead = "NONE", np.nan
        rows.append({
            "BurstId": item.BurstId,
            "error_type": outcome,
            "dominant_causal_pattern": pattern,
            "probability_A": item.probability_A,
            "lead_time_ms": lead,
            "actual": item.family,
            "prediction": item.prediction,
        })
    return pd.DataFrame(rows)


def _plot_heatmap(matrix: pd.DataFrame, title: str, path: Path, *, centered: bool = False) -> None:
    if matrix.empty:
        return
    values = matrix.to_numpy(float)
    fig, ax = plt.subplots(figsize=(max(7, matrix.shape[1] * 0.7), max(5, matrix.shape[0] * 0.6)))
    limit = np.nanmax(np.abs(values)) if centered and values.size else None
    image = ax.imshow(
        values,
        cmap="coolwarm" if centered else "Blues",
        vmin=-limit if centered and limit else None,
        vmax=limit if centered and limit else None,
        aspect="auto",
    )
    ax.set_xticks(range(len(matrix.columns)), matrix.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(matrix.index)), matrix.index)
    ax.set_title(title)
    fig.colorbar(image, ax=ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _plot_outputs(
    matrix_a: pd.DataFrame,
    matrix_b: pd.DataFrame,
    delta: pd.DataFrame,
    confusion_abs: pd.DataFrame,
    risk: pd.DataFrame,
    calibration: pd.DataFrame,
    output: Path,
) -> list[Path]:
    visual = output / "visuals"
    visual.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for matrix, name, title, centered in (
        (matrix_a, "transition_matrix_A.png", "Transiciones post-LB — A", False),
        (matrix_b, "transition_matrix_B.png", "Transiciones post-LB — B", False),
        (delta, "transition_matrix_delta.png", "Contraste A - B", True),
    ):
        path = visual / name
        _plot_heatmap(matrix, title, path, centered=centered)
        if path.exists():
            paths.append(path)
    if not confusion_abs.empty:
        matrix = confusion_abs.set_index("actual")
        path = visual / "confusion_matrix_holdout.png"
        _plot_heatmap(matrix, "Matriz de confusión — holdout", path)
        if path.exists():
            paths.append(path)
    if not risk.empty:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(risk["coverage"], risk["selective_accuracy"], marker="o")
        ax.set_xlabel("Cobertura")
        ax.set_ylabel("Exactitud selectiva")
        ax.set_ylim(0, 1.05)
        ax.grid(alpha=0.25)
        fig.tight_layout()
        path = visual / "risk_coverage_curve.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path)
    if not calibration.empty and calibration["n"].sum() > 0:
        valid = calibration.loc[calibration["n"].gt(0)]
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.plot([0, 1], [0, 1], linestyle="--", color="black")
        ax.scatter(valid["mean_probability_A"], valid["observed_frequency_A"], s=50)
        ax.set_xlabel("Probabilidad A predicha")
        ax.set_ylabel("Frecuencia A observada")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        fig.tight_layout()
        path = visual / "reliability_diagram.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path)
    return paths


def _write_csv(frame: pd.DataFrame, path: Path, *, index: bool = False) -> None:
    frame.to_csv(path, index=index)


def _markdown_table(frame: pd.DataFrame, columns: list[str], limit: int = 15) -> list[str]:
    if frame.empty:
        return ["Sin muestra suficiente."]
    columns = [column for column in columns if column in frame]
    values = frame[columns].head(limit)
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in values.itertuples(index=False, name=None):
        rendered = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                rendered.append("" if not math.isfinite(float(value)) else f"{float(value):.4f}")
            else:
                rendered.append(str(value))
        lines.append("| " + " | ".join(rendered) + " |")
    return lines


def run_analysis(
    results_folder: Path | str,
    output_folder: Path | str,
    *,
    allow_legacy: bool = False,
) -> dict[str, object]:
    results = Path(results_folder)
    output = Path(output_folder)
    output.mkdir(parents=True, exist_ok=True)
    timeline = load_timeline(results)
    audit, audit_pass, post = audit_timeline(timeline, allow_legacy=allow_legacy)
    if not audit_pass:
        audit.to_csv(output / "postburst_causal_audit.csv", index=False)
        raise RuntimeError("Post-burst causal audit failed")

    states, sequences = build_macro_states(post)
    transition_events = build_transition_events(post, states)
    labeled, outcome_audit = join_labels(results, sequences)
    label_columns = ["BurstId", "family", "split", "BurstSide", "fecha"]
    labeled_keys = labeled[[column for column in label_columns if column in labeled]].drop_duplicates("BurstId")
    labeled_transitions = transition_events.merge(labeled_keys, on="BurstId", how="inner", suffixes=("", "_label"))
    occurrences = _pattern_occurrences(states)
    transition_stats = _transition_statistics(labeled_transitions)
    pattern_matrix = _pattern_matrix(occurrences, labeled)
    bifurcations = _bifurcation_matrix(states, labeled)
    stability = _pattern_stability(occurrences, labeled)
    selection = _final_selection(pattern_matrix, stability)
    dataset, feature_sets = _feature_tables(results, labeled, labeled_transitions, occurrences)
    model_metrics, predictions = train_models(dataset, feature_sets)
    primary_validation = _primary_predictions(predictions, "validation")
    primary_holdout = _primary_predictions(predictions, "holdout")
    confusion_validation, _, _ = _confusion_outputs(primary_validation)
    confusion_holdout, normalized_holdout, abstention = _confusion_outputs(primary_holdout)
    risk = _risk_coverage(primary_holdout)
    calibration = _calibration(primary_holdout)
    by_year = _classification_slices(primary_holdout, "year")
    by_direction = _classification_slices(primary_holdout, "BurstSide")
    error_patterns = _error_patterns(primary_holdout, occurrences, selection)

    matrix_a = _pivot_transition(transition_stats, labels.FAMILY_ABSORPTION, "probability")
    matrix_b = _pivot_transition(transition_stats, labels.FAMILY_CONTINUATION, "probability")
    all_rows = sorted(set(matrix_a.index).union(matrix_b.index))
    all_cols = sorted(set(matrix_a.columns).union(matrix_b.columns))
    matrix_a = matrix_a.reindex(index=all_rows, columns=all_cols, fill_value=0.0)
    matrix_b = matrix_b.reindex(index=all_rows, columns=all_cols, fill_value=0.0)
    delta = matrix_a - matrix_b
    time_a = _pivot_transition(transition_stats, labels.FAMILY_ABSORPTION, "median_transition_time_ms")
    time_b = _pivot_transition(transition_stats, labels.FAMILY_CONTINUATION, "median_transition_time_ms")
    intensity = transition_stats[[
        column for column in (
            "family", "transition", "median_aligned_trade_volume", "median_counter_trade_volume",
            "median_ahead_add_volume", "median_ahead_remove_volume",
        ) if column in transition_stats
    ]]
    persistence = transition_stats[[
        column for column in (
            "family", "transition", "median_origin_duration_ms", "median_destination_duration_ms",
            "support_bursts", "burst_coverage",
        ) if column in transition_stats
    ]]
    price_response = transition_stats[[
        column for column in (
            "family", "transition", "price_response_100ms", "price_response_250ms",
            "price_response_500ms", "median_lead_time_ms",
        ) if column in transition_stats
    ]]

    state_dictionary = pd.DataFrame([
        {"state": state, "definition": definition, "predictor_eligible": int(state not in {"END", "CONT", "REV"})}
        for state, definition in STATE_DICTIONARY.items()
    ])
    feature_manifest = pd.DataFrame([
        {"feature_family": family, "feature": feature, "selected_without_labels": int(feature.startswith(("tr__", "sq__")))}
        for family, features in feature_sets.items() for feature in features
    ])
    optional_abc = predictions.loc[
        predictions["feature_family"].eq(PRIMARY_FEATURE_FAMILY)
        & predictions["model"].eq(PRIMARY_MODEL)
    ].copy()
    if not optional_abc.empty:
        optional_abc["prediction_with_abstention"] = np.where(
            optional_abc["confidence"].ge(ABSTENTION_CONFIDENCE), optional_abc["prediction"], "NO_DECISION"
        )
    classification_regime = pd.DataFrame([{
        "status": "OMITTED_LOW_SAMPLE",
        "reason": "Regime slicing cannot be used to rescue a global model with only 31 clean A/B labels.",
    }])

    outputs = {
        "postburst_causal_audit.csv": audit,
        "outcome_join_audit.csv": outcome_audit,
        "state_dictionary.csv": state_dictionary,
        "postburst_macro_states.csv": states,
        "postburst_sequences.csv": sequences,
        "transition_events.csv": transition_events,
        "transition_statistics.csv": transition_stats,
        "transition_matrix_A.csv": matrix_a,
        "transition_matrix_B.csv": matrix_b,
        "transition_matrix_delta.csv": delta,
        "transition_time_matrix_A.csv": time_a,
        "transition_time_matrix_B.csv": time_b,
        "transition_intensity_matrix.csv": intensity,
        "transition_persistence_matrix.csv": persistence,
        "price_response_matrix.csv": price_response,
        "bifurcation_matrix.csv": bifurcations,
        "sequence_matrix.csv": pattern_matrix,
        "stability_matrix.csv": stability,
        "final_selection_matrix.csv": selection,
        "classification_dataset.csv": dataset,
        "classification_predictions.csv": predictions,
        "feature_family_classification_matrix.csv": model_metrics,
        "feature_selection_manifest.csv": feature_manifest,
        "confusion_matrix_validation.csv": confusion_validation,
        "confusion_matrix_holdout.csv": confusion_holdout,
        "normalized_confusion_matrix_holdout.csv": normalized_holdout,
        "abstention_confusion_matrix.csv": abstention,
        "risk_coverage_matrix.csv": risk,
        "calibration_matrix.csv": calibration,
        "classification_by_year.csv": by_year,
        "classification_by_direction.csv": by_direction,
        "classification_by_regime.csv": classification_regime,
        "error_by_causal_pattern.csv": error_patterns,
        "optional_abc_diagnostic_matrix.csv": optional_abc,
    }
    for name, frame in outputs.items():
        _write_csv(frame, output / name, index=name.startswith("transition_matrix") or name.startswith("transition_time_matrix"))

    visuals = _plot_outputs(matrix_a, matrix_b, delta, confusion_holdout, risk, calibration, output)
    family_counts = labeled["family"].value_counts().to_dict() if not labeled.empty else {}
    primary_metric = model_metrics.loc[
        model_metrics.get("feature_family", pd.Series(dtype=str)).eq(PRIMARY_FEATURE_FAMILY)
        & model_metrics.get("model", pd.Series(dtype=str)).eq(PRIMARY_MODEL)
        & model_metrics.get("split", pd.Series(dtype=str)).eq("holdout")
    ] if not model_metrics.empty else pd.DataFrame()
    promising = selection.loc[selection["final_status"].eq("PROMISING")] if not selection.empty else pd.DataFrame()
    if primary_metric.empty:
        verdict = "NO_CONCLUYENTE_SIN_MODELO"
    else:
        metric = primary_metric.iloc[0]
        enough = int(metric.get("n_A", 0)) >= 20 and int(metric.get("n_B", 0)) >= 20
        strong = (
            float(metric.get("balanced_accuracy", 0)) >= 0.65
            and float(metric.get("sensitivity_A", 0)) >= 0.60
            and float(metric.get("specificity_B", 0)) >= 0.60
            and float(metric.get("balanced_accuracy_ci_low", 0)) > 0.50
            and float(metric.get("permutation_p_value", 1)) <= 0.05
        )
        verdict = "SEPARACION_RESPALDADA" if enough and strong else "PROMETEDOR_NO_CONCLUYENTE"

    report_lines = [
        "# MATRIX CLASSIFICATION TEST — patrones post-Liquidity Burst",
        "",
        f"Veredicto: **{verdict}**.",
        f"Auditoría causal: **{'PASS' if audit_pass else 'FAIL'}**.",
        f"Ventana predictora: `t_burst <= evento <= t_decision`; bin físico: {BIN_MILLISECONDS} ms.",
        f"Eventos post-LB: {len(post)}; bursts: {post['BurstId'].nunique()}; secuencias etiquetadas: {len(labeled)}.",
        f"A={family_counts.get(labels.FAMILY_ABSORPTION, 0)}; B={family_counts.get(labels.FAMILY_CONTINUATION, 0)}; C={family_counts.get(labels.FAMILY_VARIABLE, 0)}.",
        "",
        "## Qué se conservó del documento",
        "",
        "Transiciones A/B y contraste, tiempos, intensidad separada tape/DOM, persistencia, respuesta de precio aún causal, bifurcaciones, n-gramas, estabilidad, ablation, confusión, abstención, riesgo-cobertura, calibración y errores por patrón.",
        "",
        "Se omitieron FAT/REC/ACC como estados primarios porque no pueden identificarse de forma inequívoca con MBP en una ventana de ~1 s. CONT y REV siguen siendo outcomes, nunca predictores. El régimen queda diagnóstico por baja muestra.",
        "",
        "## Clasificación por familia de representación",
        "",
        *_markdown_table(model_metrics, [
            "feature_family", "model", "split", "n", "balanced_accuracy",
            "roc_auc_A_vs_B", "sensitivity_A", "specificity_B", "permutation_p_value",
        ], 20),
        "",
        "## Patrones preseleccionados sin mirar etiquetas",
        "",
        *_markdown_table(selection, [
            "pattern", "support_bursts", "delta_discovery_A_minus_B",
            "delta_validation_A_minus_B", "median_exploitable_lead_time_ms", "final_status",
        ], 20),
        "",
        "## Regla de interpretación",
        "",
        "Un accuracy alto con siete casos de holdout no prueba separación. Se exige muestra por clase, CI por encima del azar, permutación, estabilidad BUY/SELL y cobertura antes de declarar que una ruta predice A o B.",
    ]
    (output / "final_matrix_classification_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    manifest = {
        "expected_version": EXPECTED_VERSION,
        "allow_legacy": allow_legacy,
        "audit_pass": audit_pass,
        "verdict": verdict,
        "timeline_rows": len(timeline),
        "postburst_rows": len(post),
        "timeline_bursts": int(post["BurstId"].nunique()),
        "labeled_bursts": len(labeled),
        "clean_A_B": int(labeled["family"].isin(MODEL_FAMILIES).sum()) if not labeled.empty else 0,
        "promising_patterns": len(promising),
        "primary_feature_family": PRIMARY_FEATURE_FAMILY,
        "primary_model": PRIMARY_MODEL,
        "visuals": [str(path) for path in visuals],
        "output_folder": str(output),
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_folder", type=Path)
    parser.add_argument("output_folder", type=Path)
    parser.add_argument("--allow-legacy", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_analysis(args.results_folder, args.output_folder, allow_legacy=args.allow_legacy), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
