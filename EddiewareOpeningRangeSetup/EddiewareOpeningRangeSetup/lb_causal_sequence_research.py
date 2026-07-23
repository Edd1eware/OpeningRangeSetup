"""Causal DOM+tape sequence research for Liquidity Burst.

All predictors are derived only from events whose causal availability timestamp
is no later than the detector decision timestamp. Terminal MAE/MFE outcomes are
joined afterwards solely to label A/B/C.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import absorption_breakout_research as labels


EXPECTED_VERSION = "liquidity-burst-detector-2026-07-21-v6-causal-sequence"
TIMELINE_FILE = "burst_causal_timeline.csv"
RANDOM_SEED = 20260721
MODEL_FAMILIES = (labels.FAMILY_ABSORPTION, labels.FAMILY_CONTINUATION)

IDENTITY_COLUMNS = {
    "BurstId", "fecha", "family", "family_reason", "split", "ExecutionSide",
    "BurstSide", "Result_Label", "MAE_ticks", "MFE_ticks", "Initial_SL_ticks",
    "Initial_TP_ticks",
}

SEQUENCE_FEATURES = [
    "timeline_event_count", "timeline_dom_event_count", "timeline_tape_event_count",
    "timeline_duration_ms", "book_valid_fraction", "aligned_trade_fraction",
    "counter_trade_fraction", "aligned_trade_volume", "counter_trade_volume",
    "aggression_stall_fraction", "aggression_progress_fraction",
    "ahead_replenishment_count", "ahead_depletion_count",
    "ahead_replenishment_volume", "ahead_depletion_volume",
    "ahead_replenishment_share", "ahead_net_depth_change",
    "ahead_depletion_replenishment_cycles", "behind_replenishment_count",
    "behind_depletion_count", "microprice_opposed_fraction",
    "microprice_aligned_fraction", "final_directional_microprice_ticks",
    "final_directional_imbalance_l1", "final_directional_imbalance_l3",
    "final_directional_imbalance_l5", "directional_price_progress_ticks",
    "state_transition_count", "collapsed_state_count", "state_entropy",
    "first_depletion_to_replenishment_ms", "first_stall_to_replenishment_ms",
    "absorption_order_score", "breakout_order_score", "grammar_margin",
    "absorption_bigram_count", "breakout_bigram_count",
]


def _bool(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    textual = series.astype(str).str.strip().str.lower().isin({"1", "1.0", "true", "yes", "si"})
    return numeric.eq(1) | textual


def _numeric(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")


def load_timeline(results_folder: Path | str) -> pd.DataFrame:
    path = Path(results_folder) / TIMELINE_FILE
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    frame = pd.read_csv(path, low_memory=False)
    for column in (
        "Burst_Timestamp_UTC", "Decision_Timestamp_UTC", "Event_Source_Timestamp_UTC",
        "Event_Causal_Timestamp_UTC", "Event_Available_Timestamp_UTC", "Book_Snapshot_Timestamp_UTC",
    ):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    _numeric(frame, [
        "Event_Sequence_In_Burst", "Global_Arrival_Sequence", "Offset_To_Decision_Milliseconds",
        "Depth_Delta", "Trade_Volume", "Trade_Direction", "Directional_Trade_Price_Change_Ticks",
        "Directional_Microprice_Ticks", "Directional_Depth_Imbalance_L1",
        "Directional_Depth_Imbalance_L3", "Directional_Depth_Imbalance_L5",
        "Directional_Price_From_Burst_Ticks", "Book_Snapshot_Valid",
        "Available_Before_Decision", "Causal_Flag",
    ])
    if {"BurstId", "Event_Sequence_In_Burst"}.issubset(frame.columns):
        frame = frame.drop_duplicates(["BurstId", "Event_Sequence_In_Burst"], keep="last")
    return frame


def audit_timeline(timeline: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    required = {
        "Detector_VERSION", "BurstId", "Decision_Timestamp_UTC", "Event_Sequence_In_Burst",
        "Global_Arrival_Sequence", "Event_Causal_Timestamp_UTC",
        "Offset_To_Decision_Milliseconds", "Event_Type", "Event_State",
        "Available_Before_Decision", "Causal_Flag", "Model_Eligibility", "Trade_Alignment",
        "Ahead_Behind", "Depth_Delta", "Trade_Volume", "Directional_Microprice_Ticks",
        "Directional_Depth_Imbalance_L1", "Directional_Depth_Imbalance_L3",
        "Directional_Depth_Imbalance_L5", "Directional_Price_From_Burst_Ticks",
        "Book_Snapshot_Valid",
    }
    rows: list[dict[str, object]] = []

    def add(check: str, evidence: object, passed: bool) -> None:
        rows.append({"check": check, "evidence": evidence, "passed": bool(passed)})

    add("TIMELINE_PRESENT", f"rows={len(timeline)}", not timeline.empty)
    add("SCHEMA", f"required={len(required)}", required.issubset(timeline.columns))
    if timeline.empty or not required.issubset(timeline.columns):
        frame = pd.DataFrame(rows)
        return frame, False

    versions = set(timeline["Detector_VERSION"].dropna().astype(str))
    causal_time = timeline["Event_Causal_Timestamp_UTC"]
    decision_time = timeline["Decision_Timestamp_UTC"]
    offsets = pd.to_numeric(timeline["Offset_To_Decision_Milliseconds"], errors="coerce")
    causal_mask = causal_time.notna() & decision_time.notna() & causal_time.le(decision_time)
    available_mask = _bool(timeline["Available_Before_Decision"])
    flag_mask = _bool(timeline["Causal_Flag"])
    eligibility_mask = timeline["Model_Eligibility"].astype(str).eq("CAUSAL_PRE_DECISION")

    add("VERSION", sorted(versions), versions == {EXPECTED_VERSION})
    add("NO_POST_DECISION_TIME", f"violations={int((~causal_mask).sum())}", bool(causal_mask.all()))
    add("NO_POSITIVE_OFFSET", f"max_ms={offsets.max()}", bool(offsets.notna().all() and offsets.le(0.001).all()))
    add("AVAILABLE_FLAG", f"true={int(available_mask.sum())}/{len(timeline)}", bool(available_mask.all()))
    add("CAUSAL_FLAG", f"true={int(flag_mask.sum())}/{len(timeline)}", bool(flag_mask.all()))
    add("MODEL_ELIGIBILITY", f"eligible={int(eligibility_mask.sum())}/{len(timeline)}", bool(eligibility_mask.all()))
    add("UNIQUE_BURST_SEQUENCE", "BurstId+sequence unique", not timeline.duplicated(["BurstId", "Event_Sequence_In_Burst"]).any())

    consecutive = True
    monotonic_arrival = True
    monotonic_clock = True
    for _, group in timeline.groupby("BurstId", sort=False):
        group = group.sort_values("Event_Sequence_In_Burst")
        sequence = pd.to_numeric(group["Event_Sequence_In_Burst"], errors="coerce").to_numpy()
        arrival = pd.to_numeric(group["Global_Arrival_Sequence"], errors="coerce").to_numpy()
        clocks = group["Event_Causal_Timestamp_UTC"]
        consecutive &= np.array_equal(sequence, np.arange(1, len(group) + 1))
        monotonic_arrival &= bool(np.all(np.diff(arrival) > 0))
        monotonic_clock &= bool(clocks.is_monotonic_increasing)
    add("SEQUENCE_CONSECUTIVE", "each burst starts at 1 without gaps", consecutive)
    add("ARRIVAL_ORDER_STRICT", "global arrival increases within burst", monotonic_arrival)
    add("CAUSAL_CLOCK_MONOTONIC", "causal clock never moves backwards", monotonic_clock)

    event_types = set(timeline["Event_Type"].astype(str))
    has_dom = bool(event_types & {"DEPTH_INCREASE", "DEPTH_DECREASE"})
    has_tape = bool(event_types & {"TAPE_BUY", "TAPE_SELL", "TAPE_UNKNOWN"})
    add("DOM_AND_TAPE", sorted(event_types), has_dom and has_tape)
    book_valid = pd.to_numeric(timeline.get("Book_Snapshot_Valid"), errors="coerce").fillna(0).gt(0)
    add("VALID_BOOK_OBSERVED", f"valid_rows={int(book_valid.sum())}", bool(book_valid.any()))
    frame = pd.DataFrame(rows)
    return frame, bool(frame["passed"].all())


def technical_gate(results_folder: Path | str) -> tuple[pd.DataFrame, bool]:
    timeline = load_timeline(results_folder)
    audit, passed = audit_timeline(timeline)
    if not timeline.empty:
        burst_count = timeline["BurstId"].nunique()
        median_events = float(timeline.groupby("BurstId").size().median())
    else:
        burst_count = 0
        median_events = 0.0
    extra = pd.DataFrame([
        {"check": "TECHNICAL_BURSTS", "evidence": f"bursts={burst_count} expected>=2", "passed": burst_count >= 2},
        {"check": "EVENT_DENSITY", "evidence": f"median_events_per_burst={median_events:.1f} expected>=10", "passed": median_events >= 10},
    ])
    audit = pd.concat([audit, extra], ignore_index=True)
    return audit, bool(passed and extra["passed"].all())


def _collapsed(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        value = str(value)
        if not result or result[-1] != value:
            result.append(value)
    return result


def _entropy(values: list[str]) -> float:
    if not values:
        return 0.0
    counts = np.asarray(list(Counter(values).values()), dtype=float)
    probabilities = counts / counts.sum()
    return float(-(probabilities * np.log2(probabilities)).sum())


def _ordered_score(tokens: list[str], stages: list[set[str]]) -> float:
    position = 0
    matched = 0
    for stage in stages:
        found = next((index for index in range(position, len(tokens)) if tokens[index] in stage), None)
        if found is None:
            break
        matched += 1
        position = found + 1
    return matched / len(stages) if stages else 0.0


def _latency_ms(group: pd.DataFrame, first_states: set[str], second_states: set[str]) -> float:
    ordered = group.sort_values("Event_Sequence_In_Burst")
    first = ordered.loc[ordered["Event_State"].isin(first_states)]
    if first.empty:
        return np.nan
    first_sequence = first.iloc[0]["Event_Sequence_In_Burst"]
    second = ordered.loc[
        ordered["Event_State"].isin(second_states)
        & ordered["Event_Sequence_In_Burst"].gt(first_sequence)
    ]
    if second.empty:
        return np.nan
    delta = second.iloc[0]["Event_Causal_Timestamp_UTC"] - first.iloc[0]["Event_Causal_Timestamp_UTC"]
    return float(delta.total_seconds() * 1000.0)


def build_sequence_features(timeline: pd.DataFrame) -> pd.DataFrame:
    if timeline.empty:
        return pd.DataFrame(columns=["BurstId", *SEQUENCE_FEATURES])
    rows: list[dict[str, object]] = []
    for burst_id, group in timeline.groupby("BurstId", sort=False):
        group = group.sort_values("Event_Sequence_In_Burst").copy()
        states = group["Event_State"].fillna("UNKNOWN").astype(str).tolist()
        collapsed = _collapsed(states)
        state_counts = Counter(states)
        bigrams = Counter(zip(collapsed, collapsed[1:]))
        event_count = len(group)
        dom = group["Event_Type"].astype(str).str.startswith("DEPTH_")
        tape = group["Event_Type"].astype(str).str.startswith("TAPE_")
        aligned = group["Trade_Alignment"].astype(str).eq("ALIGNED") & tape
        counter = group["Trade_Alignment"].astype(str).eq("COUNTER") & tape
        trade_volume = pd.to_numeric(group["Trade_Volume"], errors="coerce").fillna(0.0)
        depth_delta = pd.to_numeric(group["Depth_Delta"], errors="coerce").fillna(0.0)
        ahead = group["Ahead_Behind"].astype(str).eq("AHEAD") & dom
        replenishment = ahead & depth_delta.gt(0)
        depletion = ahead & depth_delta.lt(0)
        behind = group["Ahead_Behind"].astype(str).eq("BEHIND") & dom
        micro = pd.to_numeric(group["Directional_Microprice_Ticks"], errors="coerce")
        valid_micro = micro.notna()
        final = group.iloc[-1]
        span = group["Event_Causal_Timestamp_UTC"].max() - group["Event_Causal_Timestamp_UTC"].min()

        absorption_stages = [
            {"AGGRESSION_PULSE", "AGGRESSION_PROGRESS", "AGGRESSION_STALL"},
            {"AGGRESSION_STALL"},
            {"DEPTH_REPLENISHMENT_AHEAD"},
        ]
        breakout_stages = [
            {"AGGRESSION_PULSE", "AGGRESSION_PROGRESS", "AGGRESSION_STALL"},
            {"DEPTH_DEPLETION_AHEAD"},
            {"AGGRESSION_PROGRESS"},
        ]
        absorption_order = _ordered_score(collapsed, absorption_stages)
        breakout_order = _ordered_score(collapsed, breakout_stages)
        final_micro = pd.to_numeric(pd.Series([final.get("Directional_Microprice_Ticks")]), errors="coerce").iloc[0]
        absorption_micro_bonus = 1.0 if pd.notna(final_micro) and final_micro < 0 else 0.0
        breakout_micro_bonus = 1.0 if pd.notna(final_micro) and final_micro > 0 else 0.0
        absorption_score = 0.75 * absorption_order + 0.25 * absorption_micro_bonus
        breakout_score = 0.75 * breakout_order + 0.25 * breakout_micro_bonus

        cycles = 0
        seen_depletion = False
        for token in collapsed:
            if token == "DEPTH_DEPLETION_AHEAD":
                seen_depletion = True
            elif token == "DEPTH_REPLENISHMENT_AHEAD" and seen_depletion:
                cycles += 1
                seen_depletion = False

        row = {
            "BurstId": burst_id,
            "timeline_event_count": event_count,
            "timeline_dom_event_count": int(dom.sum()),
            "timeline_tape_event_count": int(tape.sum()),
            "timeline_duration_ms": float(span.total_seconds() * 1000.0),
            "book_valid_fraction": float(_bool(group["Book_Snapshot_Valid"]).mean()),
            "aligned_trade_fraction": float(aligned.sum() / max(1, tape.sum())),
            "counter_trade_fraction": float(counter.sum() / max(1, tape.sum())),
            "aligned_trade_volume": float(trade_volume[aligned].sum()),
            "counter_trade_volume": float(trade_volume[counter].sum()),
            "aggression_stall_fraction": state_counts["AGGRESSION_STALL"] / max(1, int(tape.sum())),
            "aggression_progress_fraction": state_counts["AGGRESSION_PROGRESS"] / max(1, int(tape.sum())),
            "ahead_replenishment_count": int(replenishment.sum()),
            "ahead_depletion_count": int(depletion.sum()),
            "ahead_replenishment_volume": float(depth_delta[replenishment].sum()),
            "ahead_depletion_volume": float((-depth_delta[depletion]).sum()),
            "ahead_replenishment_share": float(depth_delta[replenishment].sum() / max(1.0, depth_delta[replenishment].sum() + (-depth_delta[depletion]).sum())),
            "ahead_net_depth_change": float(depth_delta[ahead].sum()),
            "ahead_depletion_replenishment_cycles": cycles,
            "behind_replenishment_count": int((behind & depth_delta.gt(0)).sum()),
            "behind_depletion_count": int((behind & depth_delta.lt(0)).sum()),
            "microprice_opposed_fraction": float(micro[valid_micro].lt(0).mean()) if valid_micro.any() else np.nan,
            "microprice_aligned_fraction": float(micro[valid_micro].gt(0).mean()) if valid_micro.any() else np.nan,
            "final_directional_microprice_ticks": final_micro,
            "final_directional_imbalance_l1": pd.to_numeric(pd.Series([final.get("Directional_Depth_Imbalance_L1")]), errors="coerce").iloc[0],
            "final_directional_imbalance_l3": pd.to_numeric(pd.Series([final.get("Directional_Depth_Imbalance_L3")]), errors="coerce").iloc[0],
            "final_directional_imbalance_l5": pd.to_numeric(pd.Series([final.get("Directional_Depth_Imbalance_L5")]), errors="coerce").iloc[0],
            "directional_price_progress_ticks": pd.to_numeric(pd.Series([final.get("Directional_Price_From_Burst_Ticks")]), errors="coerce").iloc[0],
            "state_transition_count": sum(a != b for a, b in zip(states, states[1:])),
            "collapsed_state_count": len(collapsed),
            "state_entropy": _entropy(states),
            "first_depletion_to_replenishment_ms": _latency_ms(group, {"DEPTH_DEPLETION_AHEAD"}, {"DEPTH_REPLENISHMENT_AHEAD"}),
            "first_stall_to_replenishment_ms": _latency_ms(group, {"AGGRESSION_STALL"}, {"DEPTH_REPLENISHMENT_AHEAD"}),
            "absorption_order_score": absorption_score,
            "breakout_order_score": breakout_score,
            "grammar_margin": absorption_score - breakout_score,
            "absorption_bigram_count": int(bigrams[("AGGRESSION_STALL", "DEPTH_REPLENISHMENT_AHEAD")]),
            "breakout_bigram_count": int(bigrams[("DEPTH_DEPLETION_AHEAD", "AGGRESSION_PROGRESS")]),
            "collapsed_sequence": ">".join(collapsed),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def join_outcomes(results_folder: Path | str, features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    outcome, audit = labels.build_dataset(Path(results_folder))
    if outcome.empty or features.empty:
        return pd.DataFrame(), audit
    outcome = outcome.loc[outcome["family"].isin(labels.ANALYSIS_FAMILIES)].copy()
    identity = [column for column in IDENTITY_COLUMNS if column in outcome]
    outcome = outcome[identity].drop_duplicates("BurstId", keep="last")
    return outcome.merge(features, on="BurstId", how="inner", validate="one_to_one"), audit


def _auc(y: pd.Series, score: pd.Series) -> float:
    valid = y.notna() & score.notna() & np.isfinite(score)
    if valid.sum() < 2 or y[valid].nunique() < 2:
        return np.nan
    return float(roc_auc_score(y[valid], score[valid]))


def univariate_metrics(dataset: pd.DataFrame) -> pd.DataFrame:
    clean = dataset.loc[dataset["family"].isin(MODEL_FAMILIES)].copy()
    rows: list[dict[str, object]] = []
    for feature in SEQUENCE_FEATURES:
        row: dict[str, object] = {"feature": feature}
        for split in ("discovery", "validation", "holdout", "ALL"):
            frame = clean if split == "ALL" else clean.loc[clean["split"].eq(split)]
            values = pd.to_numeric(frame.get(feature), errors="coerce")
            target = frame["family"].eq(labels.FAMILY_ABSORPTION).astype(int)
            raw_auc = _auc(target, values)
            discovery = clean.loc[clean["split"].eq("discovery")]
            discovery_a = pd.to_numeric(discovery.loc[discovery["family"].eq(labels.FAMILY_ABSORPTION), feature], errors="coerce").median()
            discovery_b = pd.to_numeric(discovery.loc[discovery["family"].eq(labels.FAMILY_CONTINUATION), feature], errors="coerce").median()
            direction = 1.0 if discovery_a >= discovery_b else -1.0
            row[f"auc_{split}"] = _auc(target, direction * values)
            row[f"n_{split}"] = int(values.notna().sum())
            row["discovery_direction"] = direction
            row[f"raw_auc_{split}"] = raw_auc
        rows.append(row)
    return pd.DataFrame(rows).sort_values("auc_discovery", ascending=False)


def model_metrics(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    clean = dataset.loc[dataset["family"].isin(MODEL_FAMILIES)].copy()
    discovery = clean.loc[clean["split"].eq("discovery")]
    rows: list[dict[str, object]] = []
    importance_rows: list[dict[str, object]] = []
    candidates = [
        feature for feature in SEQUENCE_FEATURES
        if feature in discovery and pd.to_numeric(discovery[feature], errors="coerce").notna().sum() >= 4
        and pd.to_numeric(discovery[feature], errors="coerce").nunique(dropna=True) > 1
    ]
    if len(discovery) < 8 or discovery["family"].nunique() < 2 or not candidates:
        return pd.DataFrame([{
            "model": "ALL", "split": "discovery", "status": "INSUFFICIENT_SAMPLE",
            "n": len(discovery), "classes": discovery["family"].nunique(),
        }]), pd.DataFrame()

    selected = candidates[: min(16, len(candidates))]
    imputer = SimpleImputer(strategy="median")
    x_train = imputer.fit_transform(discovery[selected].apply(pd.to_numeric, errors="coerce"))
    y_train = discovery["family"].astype(str).to_numpy()
    models: dict[str, object] = {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_SEED)),
        "random_forest": RandomForestClassifier(n_estimators=300, max_depth=3, min_samples_leaf=2, class_weight="balanced", random_state=RANDOM_SEED),
    }
    try:
        from catboost import CatBoostClassifier

        models["catboost"] = CatBoostClassifier(
            iterations=250, depth=3, learning_rate=0.03, loss_function="Logloss",
            verbose=False, random_seed=RANDOM_SEED, allow_writing_files=False,
        )
    except Exception:
        pass

    for name, model in models.items():
        model.fit(x_train, y_train)
        raw_importance = (
            np.abs(model.named_steps["logisticregression"].coef_).reshape(-1)
            if name == "logistic"
            else np.asarray(model.feature_importances_ if name == "random_forest" else model.get_feature_importance())
        )
        for feature, value in zip(selected, raw_importance):
            importance_rows.append({"model": name, "feature": feature, "importance": float(value)})

        for split in ("validation", "holdout"):
            frame = clean.loc[clean["split"].eq(split)]
            if frame.empty:
                rows.append({"model": name, "split": split, "status": "NO_ROWS", "n": 0})
                continue
            x = imputer.transform(frame[selected].apply(pd.to_numeric, errors="coerce"))
            y = frame["family"].astype(str).to_numpy()
            pred = np.asarray(model.predict(x)).reshape(-1).astype(str)
            classes = np.asarray(model.classes_).astype(str)
            probability = model.predict_proba(x)[:, int(np.flatnonzero(classes == labels.FAMILY_ABSORPTION)[0])]
            target = (y == labels.FAMILY_ABSORPTION).astype(int)
            rows.append({
                "model": name,
                "split": split,
                "status": "OK",
                "n": len(frame),
                "balanced_accuracy": balanced_accuracy_score(y, pred) if len(np.unique(y)) > 1 else np.nan,
                "roc_auc_A_vs_B": roc_auc_score(target, probability) if len(np.unique(target)) > 1 else np.nan,
                "confusion_matrix": json.dumps(confusion_matrix(y, pred, labels=list(MODEL_FAMILIES)).tolist()),
                "feature_count": len(selected),
            })
    return pd.DataFrame(rows), pd.DataFrame(importance_rows)


def sequence_patterns(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for family, frame in dataset.groupby("family"):
        counter: Counter[str] = Counter()
        for sequence in frame["collapsed_sequence"].fillna("").astype(str):
            tokens = [token for token in sequence.split(">") if token]
            counter.update(f"{a}>{b}" for a, b in zip(tokens, tokens[1:]))
        for pattern, count in counter.most_common(30):
            rows.append({"family": family, "pattern": pattern, "count": count, "bursts": len(frame)})
    return pd.DataFrame(rows)


def _plot_outputs(dataset: pd.DataFrame, univariate: pd.DataFrame, output: Path) -> list[Path]:
    visual = output / "visuals"
    visual.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    if not univariate.empty:
        plot = univariate.sort_values("auc_discovery").tail(12)
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.barh(plot["feature"], plot["auc_discovery"], color="#4c78a8", label="Discovery")
        ax.scatter(plot["auc_validation"], plot["feature"], color="#f58518", label="Validation", zorder=3)
        ax.scatter(plot["auc_holdout"], plot["feature"], color="#e45756", label="Holdout", zorder=3)
        ax.axvline(0.5, color="black", linestyle="--", linewidth=1)
        ax.set_xlim(0, 1)
        ax.set_xlabel("AUC A-vs-B (direction fixed in discovery)")
        ax.legend()
        fig.tight_layout()
        path = visual / "sequence_feature_auc.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(path)

    if not dataset.empty:
        columns = ["aggression_stall_fraction", "ahead_replenishment_share", "microprice_opposed_fraction"]
        means = dataset.loc[dataset["family"].isin(labels.ANALYSIS_FAMILIES)].groupby("family")[columns].mean()
        if not means.empty:
            ax = means.T.plot(kind="bar", figsize=(10, 6))
            ax.set_ylabel("Mean causal sequence feature")
            ax.set_xticklabels(ax.get_xticklabels(), rotation=25, ha="right")
            ax.figure.tight_layout()
            path = visual / "sequence_family_means.png"
            ax.figure.savefig(path, dpi=160)
            plt.close(ax.figure)
            paths.append(path)
    return paths


def _markdown_table(frame: pd.DataFrame, columns: list[str], limit: int = 20) -> list[str]:
    if frame.empty:
        return ["Sin muestra suficiente."]
    columns = [column for column in columns if column in frame]
    values = frame[columns].head(limit)
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in values.itertuples(index=False, name=None):
        formatted = []
        for value in row:
            if isinstance(value, float):
                formatted.append("" if not math.isfinite(value) else f"{value:.4f}")
            else:
                formatted.append(str(value))
        lines.append("| " + " | ".join(formatted) + " |")
    return lines


def run_analysis(results_folder: Path | str, output_folder: Path | str) -> dict[str, object]:
    results_folder = Path(results_folder)
    output = Path(output_folder)
    output.mkdir(parents=True, exist_ok=True)
    timeline = load_timeline(results_folder)
    audit, audit_pass = audit_timeline(timeline)
    features = build_sequence_features(timeline) if audit_pass else pd.DataFrame()
    dataset, outcome_audit = join_outcomes(results_folder, features)
    univariate = univariate_metrics(dataset) if not dataset.empty else pd.DataFrame()
    models, importance = model_metrics(dataset) if not dataset.empty else (pd.DataFrame(), pd.DataFrame())
    patterns = sequence_patterns(dataset)
    visuals = _plot_outputs(dataset, univariate, output)

    audit.to_csv(output / "causal_timeline_audit.csv", index=False)
    features.to_csv(output / "sequence_features.csv", index=False)
    dataset.to_csv(output / "sequence_dataset_labeled.csv", index=False)
    univariate.to_csv(output / "sequence_univariate_metrics.csv", index=False)
    models.to_csv(output / "sequence_model_metrics.csv", index=False)
    importance.to_csv(output / "sequence_model_importance.csv", index=False)
    patterns.to_csv(output / "sequence_patterns.csv", index=False)
    outcome_audit.to_csv(output / "outcome_join_audit.csv", index=False)

    family_counts = dataset["family"].value_counts().to_dict() if not dataset.empty else {}
    clean = dataset.loc[dataset["family"].isin(MODEL_FAMILIES)] if not dataset.empty else pd.DataFrame()
    lines = [
        "# Resultado — secuencias causales DOM+tape",
        "",
        f"Auditoría causal: **{'PASS' if audit_pass else 'FAIL'}**.",
        f"Eventos timeline: {len(timeline)}; BurstId capturados: {timeline['BurstId'].nunique() if not timeline.empty else 0}.",
        f"Casos etiquetados: {len(dataset)}; A={family_counts.get(labels.FAMILY_ABSORPTION, 0)}; B={family_counts.get(labels.FAMILY_CONTINUATION, 0)}; C={family_counts.get(labels.FAMILY_VARIABLE, 0)}.",
        "",
        "## AUC de variables secuenciales",
        "",
        *_markdown_table(univariate, ["feature", "auc_discovery", "auc_validation", "auc_holdout", "n_holdout"], 15),
        "",
        "## Modelos A-vs-B",
        "",
        *_markdown_table(models, ["model", "split", "n", "balanced_accuracy", "roc_auc_A_vs_B", "status"], 20),
        "",
        "C no entrena los modelos. Ningún evento posterior a t_decision es elegible.",
    ]
    (output / "final_sequence_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "expected_version": EXPECTED_VERSION,
        "audit_pass": audit_pass,
        "timeline_rows": len(timeline),
        "timeline_bursts": int(timeline["BurstId"].nunique()) if not timeline.empty else 0,
        "labeled_bursts": len(dataset),
        "clean_A_B": len(clean),
        "visuals": [str(path) for path in visuals],
        "output_folder": str(output),
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_folder", type=Path)
    parser.add_argument("output_folder", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_analysis(args.results_folder, args.output_folder), indent=2))
