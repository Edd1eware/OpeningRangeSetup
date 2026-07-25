"""Quote non-billable 5.1-second outcome windows for the joint A/B V4 study."""

from __future__ import annotations

import argparse
import gc
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
import pandas as pd

from download_databento_mbo_manifest import validate_key


EXCLUDED_ROLLOVER_DATES = {"2022-06-13", "2023-06-13"}
SCHEMAS = ("trades", "mbo")
MIN_FREE_BYTES = 10 * 1024**3


def build_manifest(source: pd.DataFrame) -> pd.DataFrame:
    required = {
        "fecha",
        "BurstId",
        "burst_side",
        "strategy_decision_timestamp_utc",
        "resolved_raw_symbol",
    }
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"Source manifest lacks: {sorted(missing)}")
    source = source.copy()
    source["fecha"] = source["fecha"].astype(str)
    source = source.loc[
        ~source["fecha"].isin(EXCLUDED_ROLLOVER_DATES)
    ].copy()
    if len(source) != 98 or source["BurstId"].duplicated().any():
        raise ValueError("Expected 98 unique valid BurstId")

    rows: list[dict[str, Any]] = []
    for item in source.itertuples(index=False):
        decision = pd.to_datetime(
            item.strategy_decision_timestamp_utc, utc=True, errors="raise"
        )
        for schema in SCHEMAS:
            rows.append(
                {
                    "request_id": (
                        f"NQ_JOINT_AB_V4_{schema.upper()}_"
                        f"{item.fecha}_{item.BurstId}"
                    ),
                    "fecha": str(item.fecha),
                    "year": int(str(item.fecha)[:4]),
                    "BurstId": str(item.BurstId),
                    "burst_side": str(item.burst_side),
                    "decision_utc": decision.isoformat(),
                    "dataset": "GLBX.MDP3",
                    "schema": schema,
                    "symbols": str(item.resolved_raw_symbol),
                    "stype_in": "raw_symbol",
                    "stype_out": "instrument_id",
                    "start_utc": (
                        decision - pd.Timedelta(milliseconds=100)
                    ).isoformat(),
                    "end_utc_exclusive": (
                        decision + pd.Timedelta(seconds=5)
                    ).isoformat(),
                    "window_milliseconds": 5100,
                    "purpose": "INDEPENDENT_5S_LABEL_ONLY_NEVER_PREDICTOR",
                }
            )
    manifest = pd.DataFrame(rows)
    if len(manifest) != 196 or manifest["request_id"].duplicated().any():
        raise ValueError("Expected 196 unique schema-session requests")
    return manifest


def get_cost_with_retry(
    client: db.Historical,
    row: pd.Series,
    attempts: int = 4,
) -> float:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return float(
                client.metadata.get_cost(
                    dataset=str(row["dataset"]),
                    symbols=[str(row["symbols"])],
                    schema=str(row["schema"]),
                    start=str(row["start_utc"]),
                    end=str(row["end_utc_exclusive"]),
                    stype_in=str(row["stype_in"]),
                )
            )
        except Exception as error:  # pragma: no cover
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Cost quote failed for {row['request_id']}: {last_error}")


def quote_all(
    manifest: pd.DataFrame,
    client: db.Historical,
    detail_path: Path,
) -> pd.DataFrame:
    if detail_path.exists():
        detail = pd.read_csv(detail_path)
    else:
        detail = pd.DataFrame(
            columns=[
                "request_id",
                "fecha",
                "BurstId",
                "schema",
                "symbols",
                "start_utc",
                "end_utc_exclusive",
                "estimated_cost_usd",
            ]
        )
    quoted = set(detail["request_id"].astype(str))
    records = detail.to_dict(orient="records")
    total = len(manifest)
    for position, row in manifest.iterrows():
        request_id = str(row["request_id"])
        if request_id in quoted:
            print(f"[QUOTE {position + 1}/{total}] cached {request_id}", flush=True)
            continue
        cost = get_cost_with_retry(client, row)
        records.append(
            {
                "request_id": request_id,
                "fecha": str(row["fecha"]),
                "BurstId": str(row["BurstId"]),
                "schema": str(row["schema"]),
                "symbols": str(row["symbols"]),
                "start_utc": str(row["start_utc"]),
                "end_utc_exclusive": str(row["end_utc_exclusive"]),
                "estimated_cost_usd": cost,
            }
        )
        detail = pd.DataFrame(records)
        detail.to_csv(detail_path, index=False)
        quoted.add(request_id)
        print(
            f"[QUOTE {position + 1}/{total}] {row['schema']} "
            f"{cost:.9f} USD {row['fecha']}",
            flush=True,
        )
        gc.collect()
        time.sleep(0.10)
    detail = pd.DataFrame(records)
    expected = set(manifest["request_id"].astype(str))
    if set(detail["request_id"].astype(str)) != expected:
        raise RuntimeError("Quote detail does not exactly cover manifest")
    return detail


def main() -> int:
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "DATABENTO_MBO_SNAPSHOT_DISCOVERY_100_RESOLVED_20260723.csv",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=project
        / "contexto_codex_claude"
        / "joint_ab_v4"
        / "AB_V4_OUTCOME_98_QUOTE_MANIFEST.csv",
    )
    parser.add_argument(
        "--cost-detail",
        type=Path,
        default=project
        / "contexto_codex_claude"
        / "joint_ab_v4"
        / "AB_V4_OUTCOME_98_COST_DETAIL.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=project
        / "contexto_codex_claude"
        / "joint_ab_v4"
        / "AB_V4_OUTCOME_98_COST_SUMMARY.json",
    )
    parser.add_argument(
        "--key-file",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\databento_api_key.txt"
        ),
    )
    args = parser.parse_args()

    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    source = pd.read_csv(args.source_manifest)
    manifest = build_manifest(source)
    manifest.to_csv(args.manifest_output, index=False)

    key = validate_key(args.key_file)
    detail = quote_all(manifest, db.Historical(key), args.cost_detail)
    by_schema = (
        detail.groupby("schema")["estimated_cost_usd"]
        .agg(["count", "sum", "mean", "max"])
        .reset_index()
    )
    free_bytes = shutil.disk_usage(args.manifest_output.parent).free
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "billable_download_started": False,
        "sessions": 98,
        "window_milliseconds": 5100,
        "excluded_rollover_dates": sorted(EXCLUDED_ROLLOVER_DATES),
        "cost_by_schema": by_schema.to_dict(orient="records"),
        "free_bytes": int(free_bytes),
        "free_gib": free_bytes / 1024**3,
        "reserve_10_gib_pass": free_bytes >= MIN_FREE_BYTES,
    }
    args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
