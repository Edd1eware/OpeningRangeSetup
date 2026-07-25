"""Apply the frozen V5 instrument once to the 98 diagnostic outcomes."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from joint_ab_v4_label_outcomes import (
    EXCLUDED_DATES,
    LABEL_A,
    LABEL_B,
    LABEL_C,
    _jaccard,
    label_one,
)


def v5_summary(labels: pd.DataFrame) -> dict[str, Any]:
    counts = labels["base_label"].value_counts().to_dict()
    count_a = int(counts.get(LABEL_A, 0))
    count_b = int(counts.get(LABEL_B, 0))
    count_c = int(counts.get(LABEL_C, 0))
    minimum_class_count = int(math.ceil(0.15 * len(labels)))
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
    nonprice_integrity = [
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
    gates = {
        "sessions_98": len(labels) == 98,
        "all_causal_mbo_integrity_pass": bool(
            labels[nonprice_integrity].all(axis=None)
        ),
        "A_at_least_15pct": count_a >= minimum_class_count,
        "B_at_least_15pct": count_b >= minimum_class_count,
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
        "jaccard_A_both_at_least_070": min(
            jaccards["A_low_85"], jaccards["A_high_115"]
        )
        >= 0.70,
        "jaccard_B_both_at_least_070": min(
            jaccards["B_low_85"], jaccards["B_high_115"]
        )
        >= 0.70,
    }
    return {
        "counts": {
            LABEL_A: count_a,
            LABEL_B: count_b,
            LABEL_C: count_c,
        },
        "prevalence": {
            LABEL_A: count_a / len(labels),
            LABEL_B: count_b / len(labels),
            LABEL_C: count_c / len(labels),
        },
        "minimum_class_count_15pct": minimum_class_count,
        "clean_class_max_share": (
            max(count_a, count_b) / clean if clean else None
        ),
        "jaccards": jaccards,
        "by_year": by_year.to_dict(orient="index"),
        "by_side": by_side.to_dict(orient="index"),
        "gates": gates,
        "instrument_pilot_pass": all(gates.values()),
    }


def main() -> int:
    project = Path(__file__).resolve().parent
    v4_base = project / "contexto_codex_claude" / "joint_ab_v4"
    v5_base = project / "contexto_codex_claude" / "joint_ab_v5"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=v4_base / "AB_V4_OUTCOME_98_QUOTE_MANIFEST.csv",
    )
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=v5_base / "AB_V5_FROZEN_THRESHOLDS.json",
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
        default=v5_base / "AB_V5_INSTRUMENT_DIAGNOSTIC_LABELS_98.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=v5_base / "AB_V5_INSTRUMENT_PILOT_RESULT.json",
    )
    args = parser.parse_args()

    threshold_document = json.loads(
        args.thresholds.read_text(encoding="utf-8")
    )
    if not threshold_document["calibration_pass"]:
        raise ValueError("V5 calibration did not pass")
    thresholds = threshold_document["thresholds"]
    manifest = pd.read_csv(args.manifest)
    manifest = manifest.loc[
        manifest["schema"].eq("mbo")
        & ~manifest["fecha"].astype(str).isin(EXCLUDED_DATES)
    ].sort_values(["fecha", "BurstId"]).reset_index(drop=True)
    if len(manifest) != 98:
        raise ValueError("Expected 98 diagnostic outcome rows")
    atas = pd.read_csv(args.atas_prices)
    price_by_burst = (
        atas.drop_duplicates("BurstId").set_index("BurstId")["burst_price"]
    )

    records = []
    for position, row in manifest.iterrows():
        path = args.outcome_dir / (
            f"{row['request_id']}_PAD100MS.mbo.dbn.zst"
        )
        price = price_by_burst.get(str(row["BurstId"]), np.nan)
        record = label_one(
            path,
            row,
            thresholds,
            float(price) if np.isfinite(price) else None,
        )
        record["information_status"] = (
            "INSTRUMENT_DIAGNOSTIC_NEVER_PREDICTIVE_EVIDENCE"
        )
        records.append(record)
        print(
            f"[V5 LABEL {position + 1}/98] {row['fecha']} "
            f"{record['base_label']}",
            flush=True,
        )
    labels = pd.DataFrame(records)
    args.labels_output.parent.mkdir(parents=True, exist_ok=True)
    labels.to_csv(args.labels_output, index=False)
    result = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "preregistered_design_sha256": threshold_document["design_sha256"],
        "calibration_pass": True,
        "thresholds": thresholds,
        "labels_path": str(args.labels_output),
        "predictive_model_trained": False,
        "terminal_results_used": False,
        "entry_price_vs_p0_policy": (
            "DIAGNOSTIC_SLIPPAGE_ONLY_NOT_CLOCK_GATE"
        ),
        "entry_price_vs_p0_over_2_ticks": int(
            (~labels["atas_databento_p0_within_2_ticks"]).sum()
        ),
        **v5_summary(labels),
    }
    args.summary_output.write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
