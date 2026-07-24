"""Estimate Databento manifest costs without downloading any market data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import databento as db
import pandas as pd

from download_databento_mbo_manifest import validate_key


def estimate_manifest(
    manifest: pd.DataFrame,
    key_file: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    required = {
        "request_id",
        "dataset",
        "schema",
        "symbols",
        "stype_in",
        "start_utc",
        "end_utc_exclusive",
    }
    missing = required.difference(manifest.columns)
    if missing:
        raise ValueError(f"Manifest is missing columns: {sorted(missing)}")
    client = db.Historical(validate_key(key_file))
    rows = []
    for index, row in manifest.iterrows():
        cost_usd = client.metadata.get_cost(
            dataset=str(row["dataset"]),
            symbols=[str(row["symbols"])],
            schema=str(row["schema"]),
            start=str(row["start_utc"]),
            end=str(row["end_utc_exclusive"]),
            stype_in=str(row["stype_in"]),
        )
        rows.append(
            {
                "request_id": str(row["request_id"]),
                "pilot_stage": str(row.get("pilot_stage", "")),
                "fecha": str(row.get("fecha", "")),
                "BurstId": str(row.get("BurstId", "")),
                "family_label_only": str(row.get("family_label_only", "")),
                "burst_side": str(row.get("burst_side", "")),
                "start_utc": str(row["start_utc"]),
                "end_utc_exclusive": str(row["end_utc_exclusive"]),
                "requested_hours": float(row.get("requested_hours", float("nan"))),
                "estimated_cost_usd": float(cost_usd),
            }
        )
        print(
            f"[{index + 1}/{len(manifest)}] cost estimated for "
            f"{row['request_id']}",
            flush=True,
        )
    detail = pd.DataFrame(rows)
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_rows": int(len(detail)),
        "metadata_cost_requests_performed": int(len(detail)),
        "market_data_downloaded": False,
        "billable_download_performed": False,
        "estimated_total_cost_usd": float(detail["estimated_cost_usd"].sum()),
        "estimated_mean_cost_usd": float(detail["estimated_cost_usd"].mean()),
        "estimated_min_cost_usd": float(detail["estimated_cost_usd"].min()),
        "estimated_max_cost_usd": float(detail["estimated_cost_usd"].max()),
    }
    return detail, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--key-file",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\databento_api_key.txt"
        ),
    )
    parser.add_argument("--detail-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest)
    detail, summary = estimate_manifest(manifest, args.key_file)
    args.detail_output.parent.mkdir(parents=True, exist_ok=True)
    detail.to_csv(args.detail_output, index=False)
    summary["manifest"] = str(args.manifest)
    summary["detail_output"] = str(args.detail_output)
    args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
