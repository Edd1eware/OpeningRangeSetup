"""Prepare the fixed 100-session MBO snapshot discovery manifest offline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from prepare_mbo_snapshot_pilot import (
    _stable_rank,
    build_manifest,
    excluded_holidays,
)


EXPECTED_FAMILIES = {
    "A_TRUE_ABSORPTION": 29,
    "B_CLEAN_BREAKOUT": 41,
    "C_MIXED_PATH": 30,
}
EXPECTED_YEARS = {2022: 34, 2023: 37, 2024: 29}
EXPECTED_SIDES = {"BUY": 47, "SELL": 53}


def prepare(joined_path: Path, timing_path: Path) -> pd.DataFrame:
    joined = pd.read_csv(
        joined_path,
        usecols=[
            "BurstId",
            "fecha",
            "split",
            "family",
            "burst_side",
            "burst_price",
            "reference_level",
            "causal_cutoff_utc",
            "year",
        ],
    )
    timing = pd.read_csv(
        timing_path,
        usecols=[
            "BurstId",
            "burst_timestamp_utc",
            "detector_publish_timestamp_utc",
            "prediction_timestamp",
        ],
    ).drop_duplicates("BurstId")
    frame = joined.merge(timing, on="BurstId", how="left", validate="one_to_one")
    frame["year"] = pd.to_numeric(frame["year"], errors="raise").astype(int)
    frame["fecha"] = frame["fecha"].astype(str)
    frame["burst_side"] = frame["burst_side"].astype(str).str.upper()
    frame["selection_hash"] = frame["BurstId"].map(_stable_rank)
    frame["excluded_holiday"] = frame["fecha"].isin(excluded_holidays())
    if frame["burst_timestamp_utc"].isna().any():
        raise ValueError("Missing burst timestamps")
    if len(frame) != 100 or frame["fecha"].nunique() != 100:
        raise ValueError(
            f"Expected 100 unique sessions, got rows={len(frame)} "
            f"dates={frame['fecha'].nunique()}"
        )
    if frame["excluded_holiday"].any():
        dates = frame.loc[frame["excluded_holiday"], "fecha"].tolist()
        raise ValueError(f"Discovery manifest contains excluded holidays: {dates}")
    if frame["family"].value_counts().to_dict() != EXPECTED_FAMILIES:
        raise ValueError(
            f"Unexpected family distribution: "
            f"{frame['family'].value_counts().to_dict()}"
        )
    if frame["year"].value_counts().sort_index().to_dict() != EXPECTED_YEARS:
        raise ValueError(
            f"Unexpected year distribution: "
            f"{frame['year'].value_counts().sort_index().to_dict()}"
        )
    if frame["burst_side"].value_counts().to_dict() != EXPECTED_SIDES:
        raise ValueError(
            f"Unexpected side distribution: "
            f"{frame['burst_side'].value_counts().to_dict()}"
        )
    return build_manifest(
        frame.sort_values(["fecha", "BurstId"]).reset_index(drop=True),
        "DISCOVERY_100",
    )


def main() -> int:
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--joined",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\trade_results_score\visual_tests"
            r"\04_run_replay_lb_matrix_mbo_pilot100_discovery_r1_runs"
            r"\scientific_analysis\matrix_mbo_joined_dataset.csv"
        ),
    )
    parser.add_argument(
        "--timing",
        type=Path,
        default=project
        / "outputs"
        / "preentry_liquidity_features_20260720_preentry_r2"
        / "preentry_mbp_feature_ledger.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "DATABENTO_MBO_SNAPSHOT_DISCOVERY_100_20260723.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "DATABENTO_MBO_SNAPSHOT_DISCOVERY_100_20260723.json",
    )
    args = parser.parse_args()

    manifest = prepare(args.joined, args.timing)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(args.output, index=False)
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(manifest)),
        "unique_dates": int(manifest["fecha"].nunique()),
        "families": manifest["family_label_only"].value_counts().to_dict(),
        "years": {
            str(key): int(value)
            for key, value in manifest["year"].value_counts().sort_index().items()
        },
        "sides": manifest["burst_side"].value_counts().to_dict(),
        "holiday_rows": int((~manifest["holiday_exclusion_pass"]).sum()),
        "start_midnight_utc_rows": int(
            manifest["start_utc"].str.contains("T00:00:00").sum()
        ),
        "strict_cutoff_rows": int(
            manifest["same_millisecond_policy"]
            .eq("EXCLUDE_ENTIRE_DECISION_MILLISECOND")
            .sum()
        ),
        "network_requests_performed": False,
        "market_data_downloaded": False,
        "output": str(args.output),
    }
    args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
