"""Build a no-cost manifest for narrow Databento MBO research windows.

This script performs no network requests and downloads no data. It produces one
causal interval per Liquidity Burst trade, ending immediately after the original
prediction timestamp so a downstream loader can filter `ts_event <= cutoff`.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


DATASET = "GLBX.MDP3"
SCHEMA = "mbo"
SYMBOL = "NQ.v.0"
STYPE_IN = "continuous"
STYPE_OUT = "raw_symbol"
LOOKBACK_SECONDS = 10
END_PADDING_MILLISECONDS = 1


def build_manifest(source: Path) -> pd.DataFrame:
    frame = pd.read_csv(source)
    cutoff = pd.to_datetime(frame["prediction_timestamp"], utc=True, errors="raise")
    start = cutoff - pd.to_timedelta(LOOKBACK_SECONDS, unit="s")
    end = cutoff + pd.to_timedelta(END_PADDING_MILLISECONDS, unit="ms")
    manifest = pd.DataFrame(
        {
            "request_id": [f"NQ_MBO_{date}_{burst_id}" for date, burst_id in zip(frame["fecha"], frame["BurstId"], strict=True)],
            "fecha": frame["fecha"],
            "BurstId": frame["BurstId"],
            "split": frame["split"],
            "family_label_only": frame["family"],
            "dataset": DATASET,
            "schema": SCHEMA,
            "symbols": SYMBOL,
            "stype_in": STYPE_IN,
            "stype_out": STYPE_OUT,
            "start_utc": start.dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "end_utc_exclusive": end.dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "causal_cutoff_utc_inclusive": cutoff.dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "requested_seconds": (end - start).dt.total_seconds(),
            "post_download_filter": "ts_event<=causal_cutoff_utc_inclusive",
            "predictor_policy": "PREENTRY_ONLY_NO_POST_BURST",
        }
    )
    if manifest["BurstId"].duplicated().any():
        raise ValueError("Duplicate BurstId in source")
    if not manifest["start_utc"].str[:10].eq(manifest["fecha"].astype(str)).all():
        raise ValueError("UTC date crossed unexpectedly; review intervals")
    return manifest.sort_values(["start_utc", "BurstId"]).reset_index(drop=True)


def write_outputs(manifest: pd.DataFrame, output_csv: Path, summary_json: Path) -> dict[str, object]:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(output_csv, index=False)
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "network_requests_performed": False,
        "data_downloaded": False,
        "billable_action_performed": False,
        "databento_account_status_observed": "LOCKED_403_AT_LAST_METADATA_CHECK",
        "dataset": DATASET,
        "schema": SCHEMA,
        "symbol": SYMBOL,
        "stype_in": STYPE_IN,
        "stype_out": STYPE_OUT,
        "request_rows": int(len(manifest)),
        "unique_dates": int(manifest["fecha"].nunique()),
        "total_requested_seconds": float(manifest["requested_seconds"].sum()),
        "total_requested_minutes": float(manifest["requested_seconds"].sum() / 60),
        "lookback_seconds_per_event": LOOKBACK_SECONDS,
        "end_padding_milliseconds": END_PADDING_MILLISECONDS,
        "mandatory_local_filter": "ts_event <= causal_cutoff_utc_inclusive",
        "warning": "Estimate cost with metadata.get_cost after the Databento account is unlocked; do not download before reviewing the estimate.",
        "manifest_csv": str(output_csv),
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=project / "outputs" / "absorption_breakout_research_20260720_085139" / "absorption_vs_breakout.csv",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=project / "contexto_features_atas" / "DATABENTO_MBO_VENTANAS_CAUSALES_LIQUIDITY_BURST_20260720.csv",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=project / "contexto_features_atas" / "DATABENTO_MBO_VENTANAS_CAUSALES_LIQUIDITY_BURST_20260720.json",
    )
    args = parser.parse_args()
    manifest = build_manifest(args.source)
    print(json.dumps(write_outputs(manifest, args.output_csv, args.summary_json), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
