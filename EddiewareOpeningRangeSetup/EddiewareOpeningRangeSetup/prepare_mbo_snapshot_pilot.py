"""Prepare deterministic MBO snapshot pilot manifests without downloading data.

The signal pilot is balanced across year, burst side, and clean A/B family.
Historical MBO requests start at 00:00 UTC so Databento can include the daily
synthetic snapshot. The feature cutoff is exclusive and floored to the strategy
timestamp's millisecond to avoid using events whose sub-millisecond precedence
relative to ATAS cannot be proven.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar


DATASET = "GLBX.MDP3"
SCHEMA = "mbo"
SYMBOL = "NQ.v.0"
STYPE_IN = "continuous"
STYPE_OUT = "instrument_id"
SELECTION_SEED = "MBO_SNAPSHOT_PILOT_V1_20260723"
CLEAN_FAMILIES = ("A_TRUE_ABSORPTION", "B_CLEAN_BREAKOUT")
YEARS = (2022, 2023, 2024)
SIDES = ("BUY", "SELL")
PER_CELL = 2

# CME-modified sessions not covered by the US federal calendar. Excluding them
# is conservative: the pilot is intended to compare ordinary liquid sessions.
EXTRA_CME_US_EXCLUSIONS = {
    "2022-04-15",  # Good Friday
    "2022-07-01",  # Independence Day modified schedule
    "2022-11-25",  # Day after Thanksgiving
    "2022-12-23",  # Christmas modified schedule
    "2023-04-07",  # Good Friday
    "2023-07-03",  # Independence Day modified schedule
    "2023-11-24",  # Day after Thanksgiving
    "2024-03-29",  # Good Friday
    "2024-07-03",  # Independence Day modified schedule
    "2024-11-29",  # Day after Thanksgiving
    "2024-12-24",  # Christmas modified schedule
}

# One technical case per year and side, with the class alternated so the six
# sessions also contain three A and three B examples.
TECHNICAL_CLASS_BY_YEAR_SIDE = {
    (2022, "BUY"): "A_TRUE_ABSORPTION",
    (2022, "SELL"): "B_CLEAN_BREAKOUT",
    (2023, "BUY"): "B_CLEAN_BREAKOUT",
    (2023, "SELL"): "A_TRUE_ABSORPTION",
    (2024, "BUY"): "A_TRUE_ABSORPTION",
    (2024, "SELL"): "B_CLEAN_BREAKOUT",
}


def excluded_holidays() -> set[str]:
    start = pd.Timestamp(f"{min(YEARS)}-01-01")
    end = pd.Timestamp(f"{max(YEARS)}-12-31")
    federal = USFederalHolidayCalendar().holidays(start=start, end=end)
    return {value.strftime("%Y-%m-%d") for value in federal}.union(
        EXTRA_CME_US_EXCLUSIONS
    )


def _stable_rank(burst_id: str) -> str:
    value = f"{SELECTION_SEED}|{burst_id}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _format_utc_ns(values: pd.Series) -> pd.Series:
    return values.map(
        lambda value: pd.Timestamp(value)
        .isoformat(timespec="nanoseconds")
        .replace("+00:00", "Z")
    )


def _load_candidates(joined_path: Path, timing_path: Path) -> pd.DataFrame:
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

    frame = frame.loc[
        frame["family"].isin(CLEAN_FAMILIES)
        & frame["year"].isin(YEARS)
        & frame["burst_side"].isin(SIDES)
        & ~frame["excluded_holiday"]
    ].copy()
    if frame["burst_timestamp_utc"].isna().any():
        missing = frame.loc[frame["burst_timestamp_utc"].isna(), "BurstId"].tolist()
        raise ValueError(f"Missing burst timestamps: {missing}")
    return frame


def select_signal_24(candidates: pd.DataFrame) -> pd.DataFrame:
    expected_cells = {
        (year, side, family)
        for year in YEARS
        for side in SIDES
        for family in CLEAN_FAMILIES
    }
    observed_cells = set(
        candidates[["year", "burst_side", "family"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    missing = expected_cells.difference(observed_cells)
    if missing:
        raise ValueError(f"Missing year/side/family cells: {sorted(missing)}")

    selected = (
        candidates.sort_values("selection_hash")
        .groupby(["year", "burst_side", "family"], sort=True, group_keys=False)
        .head(PER_CELL)
        .copy()
    )
    counts = selected.groupby(["year", "burst_side", "family"]).size()
    if len(selected) != 24 or not counts.eq(PER_CELL).all():
        raise ValueError(f"Signal cohort is not 24 balanced sessions: {counts.to_dict()}")
    return selected.sort_values(["year", "burst_side", "family", "selection_hash"])


def select_technical_6(signal: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (year, side), family in TECHNICAL_CLASS_BY_YEAR_SIDE.items():
        cell = signal.loc[
            signal["year"].eq(year)
            & signal["burst_side"].eq(side)
            & signal["family"].eq(family)
        ].sort_values("selection_hash")
        if cell.empty:
            raise ValueError(f"Technical cell unavailable: {(year, side, family)}")
        rows.append(cell.iloc[0])
    technical = pd.DataFrame(rows).sort_values(["year", "burst_side"])
    if len(technical) != 6 or technical["BurstId"].duplicated().any():
        raise ValueError("Technical cohort must contain six unique sessions")
    if technical["family"].value_counts().to_dict() != {
        "A_TRUE_ABSORPTION": 3,
        "B_CLEAN_BREAKOUT": 3,
    }:
        raise ValueError("Technical cohort is not class-balanced")
    return technical


def build_manifest(selected: pd.DataFrame, stage: str) -> pd.DataFrame:
    decision = pd.to_datetime(
        selected["causal_cutoff_utc"],
        utc=True,
        errors="raise",
        format="mixed",
    )
    strict_cutoff = decision.dt.floor("ms")
    burst = pd.to_datetime(
        selected["burst_timestamp_utc"],
        utc=True,
        errors="raise",
        format="mixed",
    )
    start = pd.to_datetime(
        selected["fecha"], utc=True, errors="raise", format="mixed"
    )
    if not (start.dt.hour.eq(0) & start.dt.minute.eq(0) & start.dt.second.eq(0)).all():
        raise ValueError("Historical snapshot requests must start at 00:00 UTC")
    if not strict_cutoff.gt(start).all():
        raise ValueError("Cutoff must be after UTC midnight")
    if not burst.lt(strict_cutoff).all():
        raise ValueError("Burst must occur strictly before the feature cutoff")

    manifest = pd.DataFrame(
        {
            "request_id": [
                f"NQ_MBO_SNAPSHOT_{date}_{burst_id}"
                for date, burst_id in zip(
                    selected["fecha"], selected["BurstId"], strict=True
                )
            ],
            "pilot_stage": stage,
            "selection_seed": SELECTION_SEED,
            "selection_hash": selected["selection_hash"].to_numpy(),
            "fecha": selected["fecha"].to_numpy(),
            "year": selected["year"].to_numpy(),
            "BurstId": selected["BurstId"].to_numpy(),
            "family_label_only": selected["family"].to_numpy(),
            "burst_side": selected["burst_side"].to_numpy(),
            "burst_price": selected["burst_price"].to_numpy(),
            "reference_level": selected["reference_level"].to_numpy(),
            "burst_timestamp_utc": burst.dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "strategy_decision_timestamp_utc": decision.dt.strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "strict_feature_cutoff_utc_exclusive": strict_cutoff.dt.strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "dataset": DATASET,
            "schema": SCHEMA,
            "symbols": SYMBOL,
            "stype_in": STYPE_IN,
            "stype_out": STYPE_OUT,
            "resolved_instrument_id": "",
            "resolved_raw_symbol": "",
            "symbology_resolution_status": "PENDING_METADATA_RESOLUTION",
            "start_utc": start.dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "end_utc_exclusive": strict_cutoff.dt.strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "causal_cutoff_utc_inclusive": _format_utc_ns(
                strict_cutoff - pd.to_timedelta(1, unit="ns")
            ),
            "requested_hours": (
                (strict_cutoff - start).dt.total_seconds() / 3600.0
            ),
            "require_snapshot": True,
            "holiday_exclusion_pass": True,
            "predictor_policy": "PREDECISION_ONLY_NO_MFE_MAE_TP_SL_PNL",
            "same_millisecond_policy": "EXCLUDE_ENTIRE_DECISION_MILLISECOND",
            "event_packet_policy": "ONLY_F_LAST_COMPLETED_BEFORE_EXCLUSIVE_CUTOFF",
        }
    )
    if manifest["request_id"].duplicated().any():
        raise ValueError("Duplicate request IDs")
    return manifest.sort_values(["start_utc", "BurstId"]).reset_index(drop=True)


def _write_summary(
    signal_manifest: pd.DataFrame,
    technical_manifest: pd.DataFrame,
    output_path: Path,
) -> None:
    signal_counts = (
        signal_manifest.groupby(["year", "burst_side", "family_label_only"])
        .size()
        .rename("n")
        .reset_index()
        .to_dict("records")
    )
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_requests_performed": False,
        "data_downloaded": False,
        "billable_download_performed": False,
        "selection_seed": SELECTION_SEED,
        "technical_sessions": int(len(technical_manifest)),
        "signal_sessions": int(len(signal_manifest)),
        "signal_balance": signal_counts,
        "excluded_holidays": sorted(excluded_holidays()),
        "all_selected_dates_pass_holiday_exclusion": bool(
            signal_manifest["holiday_exclusion_pass"].all()
        ),
        "snapshot_policy": "00:00:00 UTC through strict predecision cutoff",
        "same_millisecond_policy": "exclude entire strategy decision millisecond",
        "technical_manifest": str(
            output_path.parent / "DATABENTO_MBO_SNAPSHOT_TECHNICAL_6_20260723.csv"
        ),
        "signal_manifest": str(
            output_path.parent / "DATABENTO_MBO_SNAPSHOT_SIGNAL_24_20260723.csv"
        ),
    }
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


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
        "--output-dir",
        type=Path,
        default=project / "contexto_features_atas",
    )
    args = parser.parse_args()

    candidates = _load_candidates(args.joined, args.timing)
    signal = select_signal_24(candidates)
    technical = select_technical_6(signal)
    signal_manifest = build_manifest(signal, "SIGNAL_24")
    technical_manifest = build_manifest(technical, "TECHNICAL_6")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    technical_path = (
        args.output_dir / "DATABENTO_MBO_SNAPSHOT_TECHNICAL_6_20260723.csv"
    )
    signal_path = args.output_dir / "DATABENTO_MBO_SNAPSHOT_SIGNAL_24_20260723.csv"
    summary_path = (
        args.output_dir / "DATABENTO_MBO_SNAPSHOT_PILOT_SELECTION_20260723.json"
    )
    technical_manifest.to_csv(technical_path, index=False)
    signal_manifest.to_csv(signal_path, index=False)
    _write_summary(signal_manifest, technical_manifest, summary_path)

    print(
        json.dumps(
            {
                "technical_sessions": len(technical_manifest),
                "signal_sessions": len(signal_manifest),
                "technical_manifest": str(technical_path),
                "signal_manifest": str(signal_path),
                "summary": str(summary_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
