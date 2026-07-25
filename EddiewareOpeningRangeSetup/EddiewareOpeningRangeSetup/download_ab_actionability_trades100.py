"""Prepare, quote, download, and validate 100 post-decision tape windows.

The operation is resumable.  All costs are obtained before the first billable
download and the run aborts if their sum exceeds the authorized cap.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
import tempfile
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
import pandas as pd

from download_databento_mbo_manifest import validate_key


AUTHORIZED_COST_CAP_USD = 3.50
MIN_FREE_BYTES = 10 * 1024**3
ROLLOVER_OVERRIDES = {
    "2022-06-13": "NQU2",
    "2023-06-13": "NQU3",
}


def build_manifest(source: pd.DataFrame) -> pd.DataFrame:
    required = {
        "fecha",
        "BurstId",
        "family_label_only",
        "burst_side",
        "strategy_decision_timestamp_utc",
        "resolved_raw_symbol",
    }
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"Source manifest lacks columns: {sorted(missing)}")
    if len(source) != 100 or source["BurstId"].duplicated().any():
        raise ValueError("Source manifest must contain 100 unique BurstId")

    rows: list[dict[str, Any]] = []
    for row in source.itertuples(index=False):
        fecha = str(row.fecha)
        decision = pd.to_datetime(
            row.strategy_decision_timestamp_utc,
            utc=True,
            errors="raise",
        )
        symbol_original = str(row.resolved_raw_symbol)
        symbol_requested = ROLLOVER_OVERRIDES.get(fecha, symbol_original)
        start = decision - pd.Timedelta(milliseconds=100)
        end = decision + pd.Timedelta(seconds=1)
        rows.append(
            {
                "request_id": f"NQ_AB_TAPE_{fecha}_{row.BurstId}",
                "fecha": fecha,
                "year": int(fecha[:4]),
                "BurstId": str(row.BurstId),
                "family_label_only": str(row.family_label_only),
                "burst_side": str(row.burst_side),
                "decision_utc": decision.isoformat(),
                "dataset": "GLBX.MDP3",
                "schema": "trades",
                "symbols": symbol_requested,
                "source_manifest_symbol": symbol_original,
                "rollover_override_applied": symbol_requested != symbol_original,
                "stype_in": "raw_symbol",
                "stype_out": "instrument_id",
                "start_utc": start.isoformat(),
                "end_utc_exclusive": end.isoformat(),
                "window_milliseconds": 1100,
                "purpose": "POST_DECISION_OUTCOME_ONLY_NEVER_PREDICTOR",
            }
        )
    manifest = pd.DataFrame(rows)
    if manifest["request_id"].duplicated().any():
        raise ValueError("Generated duplicate request_id")
    return manifest


def _get_cost_with_retry(
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
        except Exception as error:  # pragma: no cover - network branch
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Could not quote {row['request_id']}: {last_error}")


def estimate_all_costs(
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
                "symbols",
                "start_utc",
                "end_utc_exclusive",
                "estimated_cost_usd",
            ]
        )
    quoted = set(detail["request_id"].astype(str))
    rows = detail.to_dict(orient="records")
    for position, row in manifest.iterrows():
        request_id = str(row["request_id"])
        if request_id in quoted:
            print(
                f"[COST {position + 1}/100] cached {request_id}",
                flush=True,
            )
            continue
        cost = _get_cost_with_retry(client, row)
        rows.append(
            {
                "request_id": request_id,
                "fecha": str(row["fecha"]),
                "BurstId": str(row["BurstId"]),
                "symbols": str(row["symbols"]),
                "start_utc": str(row["start_utc"]),
                "end_utc_exclusive": str(row["end_utc_exclusive"]),
                "estimated_cost_usd": cost,
            }
        )
        detail = pd.DataFrame(rows)
        detail.to_csv(detail_path, index=False)
        quoted.add(request_id)
        print(
            f"[COST {position + 1}/100] {cost:.9f} USD {request_id}",
            flush=True,
        )
        gc.collect()
        time.sleep(0.10)
    detail = pd.DataFrame(rows)
    if set(detail["request_id"].astype(str)) != set(
        manifest["request_id"].astype(str)
    ):
        raise RuntimeError("Cost detail does not cover the full manifest")
    return detail


def inspect_trade_file(
    path: Path,
    row: pd.Series,
) -> dict[str, Any]:
    store = db.DBNStore.from_file(path)
    frame = store.to_df()
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    if frame.empty:
        raise ValueError(f"Empty trades file: {path}")
    required = {"ts_event", "price", "size", "instrument_id"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Trades file missing {sorted(missing)}: {path}")
    frame["ts_event"] = pd.to_datetime(
        frame["ts_event"], utc=True, errors="raise", format="mixed"
    )
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    decision = pd.to_datetime(row["decision_utc"], utc=True)
    end = pd.to_datetime(row["end_utc_exclusive"], utc=True)
    pre = frame.loc[frame["ts_event"].lt(decision) & frame["price"].notna()]
    post = frame.loc[
        frame["ts_event"].ge(decision)
        & frame["ts_event"].lt(end)
        & frame["price"].notna()
    ]
    if pre.empty or post.empty:
        raise ValueError(
            f"Missing pre/post trade for {row['request_id']}: "
            f"pre={len(pre)}, post={len(post)}"
        )
    ids = sorted(
        int(value) for value in frame["instrument_id"].dropna().unique()
    )
    return {
        "bytes": int(path.stat().st_size),
        "records": int(len(frame)),
        "predecision_records": int(len(pre)),
        "postdecision_records": int(len(post)),
        "ts_event_min": frame["ts_event"].min().isoformat(),
        "ts_event_max": frame["ts_event"].max().isoformat(),
        "p0_last_predecision": float(pre.iloc[-1]["price"]),
        "p1_last_postdecision": float(post.iloc[-1]["price"]),
        "instrument_ids": ids,
    }


def _download_one(
    client: db.Historical,
    row: pd.Series,
    output_dir: Path,
) -> tuple[Path, str, dict[str, Any]]:
    final_path = output_dir / f"{row['request_id']}.trades.dbn.zst"
    if final_path.exists():
        return final_path, "existing_valid", inspect_trade_file(final_path, row)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{row['request_id']}.",
        suffix=".tmp",
        dir=output_dir,
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The request time range does not start at UTC midnight.*",
            )
            store = client.timeseries.get_range(
                dataset=str(row["dataset"]),
                symbols=[str(row["symbols"])],
                schema=str(row["schema"]),
                start=str(row["start_utc"]),
                end=str(row["end_utc_exclusive"]),
                stype_in=str(row["stype_in"]),
                stype_out=str(row["stype_out"]),
            )
        store.to_file(temporary)
        validation = inspect_trade_file(temporary, row)
        temporary.replace(final_path)
        return final_path, "downloaded", validation
    finally:
        if temporary.exists():
            temporary.unlink()


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
        / "contexto_features_atas"
        / "DATABENTO_AB_ACTIONABILITY_TRADES_100_20260724.csv",
    )
    parser.add_argument(
        "--cost-detail",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "DATABENTO_AB_ACTIONABILITY_TRADES_100_COST_20260724.csv",
    )
    parser.add_argument(
        "--cost-summary",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "DATABENTO_AB_ACTIONABILITY_TRADES_100_COST_20260724.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\databento_mbo\ab_actionability_trades100_20260724"
        ),
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=project
        / "contexto_features_atas"
        / "DATABENTO_AB_ACTIONABILITY_TRADES_100_RECEIPT_20260724.json",
    )
    parser.add_argument(
        "--key-file",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\databento_api_key.txt"
        ),
    )
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=AUTHORIZED_COST_CAP_USD,
    )
    args = parser.parse_args()

    source = pd.read_csv(args.source_manifest)
    manifest = build_manifest(source)
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(args.manifest_output, index=False)
    print(
        f"Manifest written: {args.manifest_output} | rows={len(manifest)} | "
        f"rollover_overrides={int(manifest['rollover_override_applied'].sum())}",
        flush=True,
    )

    key = validate_key(args.key_file)
    client = db.Historical(key)
    detail = estimate_all_costs(manifest, client, args.cost_detail)
    total_cost = float(detail["estimated_cost_usd"].sum())
    cost_summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_rows": int(len(detail)),
        "schema": "trades",
        "estimated_total_cost_usd": total_cost,
        "authorized_cap_usd": float(args.max_cost_usd),
        "within_authorized_cap": total_cost <= args.max_cost_usd,
        "billable_download_started": False,
    }
    args.cost_summary.write_text(
        json.dumps(cost_summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(cost_summary, indent=2), flush=True)
    if total_cost > args.max_cost_usd:
        raise RuntimeError(
            f"Estimated cost {total_cost:.6f} exceeds cap "
            f"{args.max_cost_usd:.6f}; no data downloaded"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    free_before = shutil.disk_usage(args.output_dir).free
    if free_before < MIN_FREE_BYTES:
        raise RuntimeError(
            f"Only {free_before / 1024**3:.2f} GiB free; "
            "10 GiB reserve would be violated"
        )
    cost_summary["billable_download_started"] = True
    args.cost_summary.write_text(
        json.dumps(cost_summary, indent=2), encoding="utf-8"
    )

    receipt: dict[str, Any] = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": str(args.manifest_output),
        "estimated_total_cost_usd": total_cost,
        "authorized_cap_usd": float(args.max_cost_usd),
        "free_bytes_before": int(free_before),
        "rows": {},
    }
    if args.receipt.exists():
        prior = json.loads(args.receipt.read_text(encoding="utf-8"))
        if isinstance(prior.get("rows"), dict):
            receipt["rows"] = prior["rows"]

    for position, row in manifest.iterrows():
        free_now = shutil.disk_usage(args.output_dir).free
        if free_now < MIN_FREE_BYTES:
            raise RuntimeError(
                f"10 GiB disk reserve reached at row {position + 1}"
            )
        path, status, validation = _download_one(client, row, args.output_dir)
        receipt["rows"][str(row["request_id"])] = {
            "status": status,
            "path": str(path),
            "BurstId": str(row["BurstId"]),
            "symbol": str(row["symbols"]),
            "rollover_override_applied": bool(
                row["rollover_override_applied"]
            ),
            **validation,
        }
        args.receipt.write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )
        print(
            f"[DATA {position + 1}/100] {status} {row['request_id']} "
            f"records={validation['records']} "
            f"pre={validation['predecision_records']} "
            f"post={validation['postdecision_records']}",
            flush=True,
        )

    rows = receipt["rows"]
    receipt["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    receipt["completed_rows"] = int(len(rows))
    receipt["downloaded_rows"] = int(
        sum(value["status"] == "downloaded" for value in rows.values())
    )
    receipt["existing_valid_rows"] = int(
        sum(value["status"] == "existing_valid" for value in rows.values())
    )
    receipt["total_records"] = int(
        sum(value["records"] for value in rows.values())
    )
    receipt["total_bytes"] = int(
        sum(value["bytes"] for value in rows.values())
    )
    receipt["free_bytes_after"] = int(shutil.disk_usage(args.output_dir).free)
    receipt["reserve_10gib_respected"] = (
        receipt["free_bytes_after"] >= MIN_FREE_BYTES
    )
    args.receipt.write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: receipt[key]
                for key in [
                    "completed_rows",
                    "downloaded_rows",
                    "existing_valid_rows",
                    "total_records",
                    "total_bytes",
                    "free_bytes_after",
                    "reserve_10gib_respected",
                ]
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

