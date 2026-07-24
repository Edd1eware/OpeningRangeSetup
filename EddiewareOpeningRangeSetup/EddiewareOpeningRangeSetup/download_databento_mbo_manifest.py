"""Download and validate narrow Databento MBO windows from a CSV manifest.

The API key is read from a file and is never printed. Existing valid DBN files
are skipped, making the operation safe to resume after interruption.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import warnings
from datetime import datetime, timezone
from pathlib import Path

import databento as db
import pandas as pd


def validate_key(key_file: Path) -> str:
    key = key_file.read_text(encoding="utf-8-sig").strip()
    if not key or key == "PEGA_AQUI_LA_API_KEY_DE_DATABENTO":
        raise ValueError("Databento API key file is empty or still contains the placeholder")
    return key


def inspect_dbn(
    path: Path,
    cutoff_text: str,
    *,
    require_snapshot: bool = False,
    expected_stype_out: str | None = None,
    expected_instrument_id: int | None = None,
) -> dict[str, object]:
    store = db.DBNStore.from_file(path)
    actual_stype_out = str(store.metadata.stype_out)
    if expected_stype_out and actual_stype_out.lower() != expected_stype_out.lower():
        raise ValueError(
            f"DBN stype_out={actual_stype_out!r}, expected "
            f"{expected_stype_out!r}: {path}"
        )
    frame = store.to_df()
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    if frame.empty:
        raise ValueError(f"Downloaded DBN contains no MBO records: {path}")
    frame["ts_event"] = pd.to_datetime(frame["ts_event"], utc=True)
    cutoff = pd.Timestamp(cutoff_text)
    causal_records = int(frame["ts_event"].le(cutoff).sum())
    post_cutoff = int(frame["ts_event"].gt(cutoff).sum())
    if not causal_records:
        raise ValueError(f"DBN contains no records at or before the causal cutoff: {path}")
    flags = pd.to_numeric(frame["flags"], errors="coerce").fillna(0).astype("uint8")
    snapshot_mask = flags.map(
        lambda value: bool(value & int(db.RecordFlags.F_SNAPSHOT))
    )
    snapshot_last_mask = snapshot_mask & flags.map(
        lambda value: bool(value & int(db.RecordFlags.F_LAST))
    )
    snapshot_rows = int(snapshot_mask.sum())
    snapshot_clear_rows = int(
        (snapshot_mask & frame["action"].astype(str).eq("R")).sum()
    )
    snapshot_add_rows = int(
        (snapshot_mask & frame["action"].astype(str).eq("A")).sum()
    )
    snapshot_last_rows = int(snapshot_last_mask.sum())
    if require_snapshot and not (
        snapshot_rows > 0
        and snapshot_clear_rows > 0
        and snapshot_add_rows > 0
        and snapshot_last_rows > 0
    ):
        raise ValueError(
            "Required historical MBO snapshot is incomplete "
            f"(rows={snapshot_rows}, R={snapshot_clear_rows}, "
            f"A={snapshot_add_rows}, F_LAST={snapshot_last_rows}): {path}"
        )
    instrument_ids = [
        int(value) for value in frame["instrument_id"].dropna().unique()
    ]
    if (
        expected_instrument_id is not None
        and expected_instrument_id not in instrument_ids
    ):
        raise ValueError(
            f"Expected instrument_id={expected_instrument_id}, observed "
            f"{instrument_ids}: {path}"
        )
    return {
        "bytes": path.stat().st_size,
        "records": int(len(frame)),
        "causal_records": causal_records,
        "ts_event_min": frame["ts_event"].min().isoformat(),
        "ts_event_max": frame["ts_event"].max().isoformat(),
        "records_post_cutoff": post_cutoff,
        "actions": {str(k): int(v) for k, v in frame["action"].value_counts().items()},
        "instrument_ids": instrument_ids,
        "expected_instrument_id": expected_instrument_id,
        "metadata_stype_out": actual_stype_out,
        "snapshot_rows": snapshot_rows,
        "snapshot_clear_rows": snapshot_clear_rows,
        "snapshot_add_rows": snapshot_add_rows,
        "snapshot_last_rows": snapshot_last_rows,
        "snapshot_required": bool(require_snapshot),
    }


def output_path(output_dir: Path, request_id: str) -> Path:
    return output_dir / f"{request_id}.mbo.dbn.zst"


def request_kwargs(row: pd.Series) -> dict[str, object]:
    """Build the exact Databento request, including output symbol mapping."""
    return {
        "dataset": str(row["dataset"]),
        "symbols": [str(row["symbols"])],
        "schema": str(row["schema"]),
        "start": str(row["start_utc"]),
        "end": str(row["end_utc_exclusive"]),
        "stype_in": str(row["stype_in"]),
        "stype_out": str(row["stype_out"]),
    }


def main() -> int:
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--key-file",
        type=Path,
        default=Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\databento_api_key.txt"),
    )
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest)
    required = {
        "request_id", "dataset", "schema", "symbols", "stype_in",
        "start_utc", "end_utc_exclusive", "causal_cutoff_utc_inclusive",
        "stype_out",
    }
    missing = required.difference(manifest.columns)
    if missing:
        raise ValueError(f"Manifest is missing columns: {sorted(missing)}")
    if manifest["request_id"].duplicated().any():
        raise ValueError("Manifest contains duplicate request_id values")

    key = validate_key(args.key_file)
    client = db.Historical(key)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.receipt or args.output_dir / "download_receipt.json"
    receipt: dict[str, object] = {
        "manifest": str(args.manifest),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_key_logged": False,
        "rows": {},
    }

    for position, row in manifest.iterrows():
        request_id = str(row["request_id"])
        final_path = output_path(args.output_dir, request_id)
        require_snapshot = str(row.get("require_snapshot", "")).strip().lower() in {
            "1", "true", "yes", "si",
        }
        expected_stype_out = str(row["stype_out"])
        expected_instrument_id = None
        raw_expected_id = row.get("resolved_instrument_id")
        if pd.notna(raw_expected_id) and str(raw_expected_id).strip():
            expected_instrument_id = int(float(raw_expected_id))
        expected_raw_symbol = str(row.get("resolved_raw_symbol", "")).strip()
        if require_snapshot and not expected_raw_symbol:
            raise ValueError(
                f"Snapshot request lacks resolved_raw_symbol: {request_id}"
            )
        status = "downloaded"
        if final_path.exists():
            validation = inspect_dbn(
                final_path,
                str(row["causal_cutoff_utc_inclusive"]),
                require_snapshot=require_snapshot,
                expected_stype_out=expected_stype_out,
                expected_instrument_id=expected_instrument_id,
            )
            status = "existing_valid"
        else:
            fd, temporary_name = tempfile.mkstemp(prefix=f".{request_id}.", suffix=".tmp", dir=args.output_dir)
            os.close(fd)
            temporary_path = Path(temporary_name)
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="The request time range does not start at UTC midnight.*")
                    store = client.timeseries.get_range(**request_kwargs(row))
                store.to_file(temporary_path)
                validation = inspect_dbn(
                    temporary_path,
                    str(row["causal_cutoff_utc_inclusive"]),
                    require_snapshot=require_snapshot,
                    expected_stype_out=expected_stype_out,
                    expected_instrument_id=expected_instrument_id,
                )
                temporary_path.replace(final_path)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()

        receipt["rows"][request_id] = {
            "status": status,
            "path": str(final_path),
            "resolved_raw_symbol": expected_raw_symbol,
            **validation,
        }
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(
            f"[{position + 1}/{len(manifest)}] {status}: {request_id} "
            f"records={validation['records']} bytes={validation['bytes']}",
            flush=True,
        )

    rows = receipt["rows"]
    receipt["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    receipt["completed_rows"] = len(rows)
    receipt["total_records"] = sum(int(item["records"]) for item in rows.values())
    receipt["total_bytes"] = sum(int(item["bytes"]) for item in rows.values())
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({
        "completed_rows": receipt["completed_rows"],
        "total_records": receipt["total_records"],
        "total_bytes": receipt["total_bytes"],
        "receipt": str(receipt_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
