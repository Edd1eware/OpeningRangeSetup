"""Build the frozen independent five-second A/B/C outcome taxonomy."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
import numpy as np
import pandas as pd

from download_joint_ab_outcome_padding96 import (
    F_LAST,
    F_MAYBE_BAD_BOOK,
    _match_event_tables,
    _normalize,
)


TICK_SIZE = 0.25
EXCLUDED_DATES = {"2022-06-13", "2023-06-13"}
LABEL_A = "A_ABSORCION_LIMPIA"
LABEL_B = "B_BREAKOUT_LIMPIO"
LABEL_C = "C_VARIABLE"
HASH_COLUMNS = [
    "ts_event",
    "sequence",
    "record_ordinal",
    "side",
    "price",
    "size",
    "flags",
]


def _used_event_sha(frame: pd.DataFrame) -> str:
    payload = frame.loc[:, HASH_COLUMNS].to_csv(
        index=False, lineterminator="\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _first_dwell_completion(
    times: pd.Series,
    values: np.ndarray,
    start_index: int,
    condition,
    dwell_seconds: float,
    window_end: pd.Timestamp,
) -> tuple[pd.Timestamp | None, int | None]:
    run_start: pd.Timestamp | None = None
    for index in range(start_index, len(values)):
        timestamp = times.iloc[index]
        if condition(float(values[index])):
            if run_start is None:
                run_start = timestamp
            next_timestamp = (
                times.iloc[index + 1]
                if index + 1 < len(values)
                else window_end
            )
            completion = run_start + pd.Timedelta(seconds=dwell_seconds)
            if next_timestamp >= completion:
                return completion, index
        else:
            run_start = None
    return None, None


def classify_path(
    times: pd.Series,
    prices: np.ndarray,
    p0: float,
    side: str,
    window_end: pd.Timestamp,
    thresholds: dict[str, float],
    scale: float = 1.0,
) -> dict[str, Any]:
    orientation = 1.0 if side == "BUY" else -1.0
    directional_ticks = orientation * (prices - p0) / TICK_SIZE
    push_threshold = thresholds["T_push_ticks"] * scale
    extension_threshold = thresholds["T_ext_ticks"] * scale
    return_threshold = thresholds["T_ret_ticks"] * scale
    dwell_b = thresholds["T_dwB_seconds"] * scale
    dwell_a = thresholds["T_dwA_seconds"] * scale

    push_indices = np.flatnonzero(directional_ticks >= push_threshold)
    if len(push_indices) == 0:
        return {
            "label": LABEL_C,
            "tau_push": None,
            "tau_A": None,
            "tau_B": None,
            "max_directional_ticks": float(directional_ticks.max()),
            "min_directional_ticks": float(directional_ticks.min()),
        }
    push_index = int(push_indices[0])
    tau_b, _ = _first_dwell_completion(
        times,
        directional_ticks,
        push_index,
        lambda value: value >= extension_threshold,
        dwell_b,
        window_end,
    )
    tau_a, _ = _first_dwell_completion(
        times,
        directional_ticks,
        push_index + 1,
        lambda value: value <= -return_threshold,
        dwell_a,
        window_end,
    )
    if tau_a is not None and (tau_b is None or tau_a < tau_b):
        label = LABEL_A
    elif tau_b is not None and (tau_a is None or tau_b < tau_a):
        label = LABEL_B
    else:
        label = LABEL_C
    return {
        "label": label,
        "tau_push": times.iloc[push_index],
        "tau_A": tau_a,
        "tau_B": tau_b,
        "max_directional_ticks": float(directional_ticks.max()),
        "min_directional_ticks": float(directional_ticks.min()),
    }


def _iso(value: pd.Timestamp | None) -> str | None:
    return None if value is None else value.isoformat()


def label_one(
    path: Path,
    row: pd.Series,
    thresholds: dict[str, float],
    atas_price: float | None,
) -> dict[str, Any]:
    frame = _normalize(db.DBNStore.from_file(path).to_df())
    second_decode = _normalize(db.DBNStore.from_file(path).to_df())
    deterministic = _used_event_sha(frame) == _used_event_sha(second_decode)
    decision = pd.to_datetime(row["decision_utc"], utc=True)
    window_end = decision + pd.Timedelta(seconds=5)
    last_sales, summary = _match_event_tables(frame)
    p0_candidates = last_sales.loc[
        last_sales["ts_event"].ge(decision - pd.Timedelta(milliseconds=100))
        & last_sales["ts_event"].lt(decision)
    ]
    post = last_sales.loc[
        last_sales["ts_event"].ge(decision)
        & last_sales["ts_event"].lt(window_end)
    ].copy()
    if p0_candidates.empty or post.empty:
        raise ValueError(
            f"Missing p0/post T events for {row['request_id']}"
        )
    p0 = p0_candidates.iloc[-1]
    used_ids = pd.Index(
        [int(p0["match_event_id"])]
        + [int(value) for value in post["match_event_id"]]
    ).unique()
    used_quality = summary.loc[used_ids]
    p0_lag_ms = (decision - p0["ts_event"]).total_seconds() * 1000.0
    bad_book = int(((frame["flags"] & F_MAYBE_BAD_BOOK) != 0).sum())
    regressions = int(
        (np.diff(frame["sequence"].astype("int64").to_numpy()) < 0).sum()
    )
    integrity = {
        "record_ordinal_unique": not frame["record_ordinal"].duplicated().any(),
        "used_match_events_closed": bool(used_quality["closed"].all()),
        "used_match_events_single_ts_event": bool(
            (used_quality["timestamp_count"] == 1).all()
        ),
        "maybe_bad_book_zero": bad_book == 0,
        "sequence_regressions_zero": regressions == 0,
        "double_decode_deterministic": deterministic,
        "p0_within_prior_100ms": 0.0 < p0_lag_ms <= 100.0,
        "post_trade_available": len(post) > 0,
        "contract_single": frame["instrument_id"].nunique() == 1,
    }
    symbols = (
        sorted(str(value) for value in frame["symbol"].dropna().unique())
        if "symbol" in frame.columns
        else []
    )
    integrity["contract_symbol_match"] = (
        not symbols or symbols == [str(row["symbols"])]
    )
    discrepancy_ticks = (
        abs(float(atas_price) - float(p0["price"])) / TICK_SIZE
        if atas_price is not None and np.isfinite(atas_price)
        else np.nan
    )
    integrity["atas_databento_p0_within_2_ticks"] = bool(
        np.isfinite(discrepancy_ticks) and discrepancy_ticks <= 2.0
    )
    if not all(
        value
        for key, value in integrity.items()
        if key != "atas_databento_p0_within_2_ticks"
    ):
        failed = [key for key, value in integrity.items() if not value]
        raise ValueError(f"Outcome integrity failed: {failed}")

    times = post["ts_event"].reset_index(drop=True)
    prices = post["price"].astype(float).to_numpy()
    base = classify_path(
        times,
        prices,
        float(p0["price"]),
        str(row["burst_side"]),
        window_end,
        thresholds,
        1.0,
    )
    low = classify_path(
        times,
        prices,
        float(p0["price"]),
        str(row["burst_side"]),
        window_end,
        thresholds,
        0.85,
    )
    high = classify_path(
        times,
        prices,
        float(p0["price"]),
        str(row["burst_side"]),
        window_end,
        thresholds,
        1.15,
    )
    return {
        "request_id": str(row["request_id"]),
        "BurstId": str(row["BurstId"]),
        "fecha": str(row["fecha"]),
        "year": int(row["year"]),
        "burst_side": str(row["burst_side"]),
        "resolved_raw_symbol": str(row["symbols"]),
        "outcome_file": str(path),
        "decision_utc": decision.isoformat(),
        "p0_ts_event": p0["ts_event"].isoformat(),
        "p0_price_databento": float(p0["price"]),
        "p0_lag_ms": float(p0_lag_ms),
        "atas_decision_price": atas_price,
        "atas_databento_p0_abs_ticks": float(discrepancy_ticks),
        "post_t_match_events": int(len(post)),
        "base_label": base["label"],
        "low_85_label": low["label"],
        "high_115_label": high["label"],
        "tau_push": _iso(base["tau_push"]),
        "tau_A": _iso(base["tau_A"]),
        "tau_B": _iso(base["tau_B"]),
        "max_directional_ticks": base["max_directional_ticks"],
        "min_directional_ticks": base["min_directional_ticks"],
        **integrity,
        "information_status": "OUTCOME_ONLY_NEVER_PREDICTOR",
    }


def _jaccard(
    labels: pd.DataFrame, reference: str, candidate_column: str
) -> float:
    base = set(labels.loc[labels["base_label"].eq(reference), "BurstId"])
    candidate = set(
        labels.loc[labels[candidate_column].eq(reference), "BurstId"]
    )
    union = base | candidate
    return len(base & candidate) / len(union) if union else 1.0


def taxonomy_summary(labels: pd.DataFrame) -> dict[str, Any]:
    counts = labels["base_label"].value_counts().to_dict()
    count_a = int(counts.get(LABEL_A, 0))
    count_b = int(counts.get(LABEL_B, 0))
    clean = count_a + count_b
    jaccards = {
        "A_low_85": _jaccard(labels, LABEL_A, "low_85_label"),
        "A_high_115": _jaccard(labels, LABEL_A, "high_115_label"),
        "B_low_85": _jaccard(labels, LABEL_B, "low_85_label"),
        "B_high_115": _jaccard(labels, LABEL_B, "high_115_label"),
    }
    by_year = (
        labels.groupby(["year", "base_label"]).size().unstack(fill_value=0)
    )
    by_side = (
        labels.groupby(["burst_side", "base_label"])
        .size()
        .unstack(fill_value=0)
    )
    gates = {
        "sessions_98": len(labels) == 98,
        "all_non_price_integrity_pass": bool(
            labels[
                [
                    "record_ordinal_unique",
                    "used_match_events_closed",
                    "used_match_events_single_ts_event",
                    "maybe_bad_book_zero",
                    "sequence_regressions_zero",
                    "double_decode_deterministic",
                    "p0_within_prior_100ms",
                    "post_trade_available",
                    "contract_single",
                    "contract_symbol_match",
                ]
            ].all(axis=None)
        ),
        "atas_databento_p0_all_within_2_ticks": bool(
            labels["atas_databento_p0_within_2_ticks"].all()
        ),
        "jaccard_A_both_at_least_070": min(
            jaccards["A_low_85"], jaccards["A_high_115"]
        )
        >= 0.70,
        "jaccard_B_both_at_least_070": min(
            jaccards["B_low_85"], jaccards["B_high_115"]
        )
        >= 0.70,
        "at_least_15_A": count_a >= 15,
        "at_least_15_B": count_b >= 15,
        "no_clean_class_over_70pct": bool(
            clean > 0 and max(count_a, count_b) / clean <= 0.70
        ),
        "A_and_B_each_year": all(
            int(by_year.get(LABEL_A, pd.Series()).get(year, 0)) > 0
            and int(by_year.get(LABEL_B, pd.Series()).get(year, 0)) > 0
            for year in (2022, 2023, 2024)
        ),
        "A_and_B_each_side": all(
            int(by_side.get(LABEL_A, pd.Series()).get(side, 0)) > 0
            and int(by_side.get(LABEL_B, pd.Series()).get(side, 0)) > 0
            for side in ("BUY", "SELL")
        ),
    }
    return {
        "counts": {
            LABEL_A: count_a,
            LABEL_B: count_b,
            LABEL_C: int(counts.get(LABEL_C, 0)),
        },
        "clean_class_max_share": (
            max(count_a, count_b) / clean if clean else None
        ),
        "jaccards": jaccards,
        "by_year": by_year.to_dict(orient="index"),
        "by_side": by_side.to_dict(orient="index"),
        "gates": gates,
        "taxonomy_pass": all(gates.values()),
    }


def main() -> int:
    project = Path(__file__).resolve().parent
    base = project / "contexto_codex_claude" / "joint_ab_v4"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=base / "AB_V4_OUTCOME_98_QUOTE_MANIFEST.csv",
    )
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=base / "AB_V4_FROZEN_THRESHOLDS.json",
    )
    parser.add_argument(
        "--atas-prices",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\trade_results_score\visual_tests"
            r"\04_run_replay_lb_matrix_mbo_pilot100_discovery_r1_runs"
            r"\scientific_analysis\matrix_mbo_joined_dataset.csv"
        ),
    )
    parser.add_argument(
        "--outcome-dir",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\databento_mbo\joint_ab_v4_outcome98_20260724"
        ),
    )
    parser.add_argument(
        "--labels-output",
        type=Path,
        default=base / "AB_V4_INDEPENDENT_OUTCOME_LABELS_98.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=base / "AB_V4_TAXONOMY_GATE_RESULT.json",
    )
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest)
    manifest = manifest.loc[
        manifest["schema"].eq("mbo")
        & ~manifest["fecha"].astype(str).isin(EXCLUDED_DATES)
    ].sort_values(["fecha", "BurstId"])
    if len(manifest) != 98:
        raise ValueError("Expected 98 MBO outcome rows")
    threshold_document = json.loads(
        args.thresholds.read_text(encoding="utf-8")
    )
    if not threshold_document["calibration_pass"]:
        raise ValueError("Frozen calibration did not pass")
    thresholds = threshold_document["thresholds"]
    atas = pd.read_csv(args.atas_prices)
    if "burst_price" not in atas.columns:
        raise ValueError("Frozen ATAS dataset lacks decision/burst price")
    atas_price_by_burst = (
        atas.drop_duplicates("BurstId").set_index("BurstId")["burst_price"]
    )

    records = []
    first_two_dates = {"2022-04-05", "2022-04-06"}
    for position, row in manifest.reset_index(drop=True).iterrows():
        padded_id = f"{row['request_id']}_PAD100MS"
        path = args.outcome_dir / f"{padded_id}.mbo.dbn.zst"
        if not path.exists():
            raise FileNotFoundError(path)
        price = atas_price_by_burst.get(str(row["BurstId"]), np.nan)
        records.append(
            label_one(
                path,
                row,
                thresholds,
                float(price) if np.isfinite(price) else None,
            )
        )
        print(
            f"[LABEL {position + 1}/98] {row['fecha']} "
            f"{records[-1]['base_label']} "
            f"p0diff={records[-1]['atas_databento_p0_abs_ticks']:.1f}t",
            flush=True,
        )
    labels = pd.DataFrame(records)
    labels.to_csv(args.labels_output, index=False)
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "design_sha256": threshold_document["design_sha256"],
        "thresholds": thresholds,
        "labels_path": str(args.labels_output),
        "p0_price_source": (
            "matrix_mbo_joined_dataset.burst_price; integrity only, "
            "never predictor"
        ),
        "max_atas_databento_p0_abs_ticks": float(
            labels["atas_databento_p0_abs_ticks"].max()
        ),
        "sessions_over_2_ticks": int(
            (~labels["atas_databento_p0_within_2_ticks"]).sum()
        ),
        **taxonomy_summary(labels),
    }
    args.summary_output.write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
