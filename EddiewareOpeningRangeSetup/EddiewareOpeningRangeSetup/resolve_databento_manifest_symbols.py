"""Resolve continuous futures to instrument ID and raw contract using metadata.

This script performs symbology metadata requests only. It downloads no market
data. The output manifest requests the resolved raw contract directly and keeps
MBO records keyed by instrument_id, a supported Databento combination.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import databento as db
import pandas as pd

from download_databento_mbo_manifest import validate_key


def _resolved_symbol(payload: dict, input_symbol: str) -> str:
    if int(payload.get("status", -1)) != 0:
        raise ValueError(f"Symbology request failed: {payload}")
    if payload.get("not_found"):
        raise ValueError(f"Symbology not found: {payload['not_found']}")
    intervals = payload.get("result", {}).get(str(input_symbol), [])
    symbols = {str(item["s"]) for item in intervals if item.get("s") not in (None, "")}
    if len(symbols) != 1:
        raise ValueError(
            f"Expected one mapping for {input_symbol}, received {sorted(symbols)}"
        )
    return symbols.pop()


def resolve_manifest(
    manifest: pd.DataFrame,
    key_file: Path,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    client = db.Historical(validate_key(key_file))
    resolved = manifest.copy()
    audit_rows = []
    for index, row in resolved.iterrows():
        date_value = pd.Timestamp(str(row["fecha"])).date()
        end_date = date_value + timedelta(days=1)
        continuous_symbol = str(row["symbols"])
        first = client.symbology.resolve(
            dataset=str(row["dataset"]),
            symbols=[continuous_symbol],
            stype_in=str(row["stype_in"]),
            stype_out="instrument_id",
            start_date=date_value.isoformat(),
            end_date=end_date.isoformat(),
        )
        instrument_text = _resolved_symbol(first, continuous_symbol)
        instrument_id = int(instrument_text)
        second = client.symbology.resolve(
            dataset=str(row["dataset"]),
            symbols=[instrument_id],
            stype_in="instrument_id",
            stype_out="raw_symbol",
            start_date=date_value.isoformat(),
            end_date=end_date.isoformat(),
        )
        raw_symbol = _resolved_symbol(second, str(instrument_id))

        resolved.at[index, "continuous_symbol"] = continuous_symbol
        resolved.at[index, "symbols"] = raw_symbol
        resolved.at[index, "stype_in"] = "raw_symbol"
        resolved.at[index, "stype_out"] = "instrument_id"
        resolved.at[index, "resolved_instrument_id"] = instrument_id
        resolved.at[index, "resolved_raw_symbol"] = raw_symbol
        resolved.at[index, "symbology_resolution_status"] = "RESOLVED_TWO_STEP"
        audit_rows.append(
            {
                "request_id": str(row["request_id"]),
                "fecha": str(row["fecha"]),
                "continuous_symbol": continuous_symbol,
                "resolved_instrument_id": instrument_id,
                "resolved_raw_symbol": raw_symbol,
                "continuous_to_instrument_status": int(first.get("status", -1)),
                "instrument_to_raw_status": int(second.get("status", -1)),
                "market_data_downloaded": False,
            }
        )
        print(
            f"[{index + 1}/{len(resolved)}] symbology resolved for "
            f"{row['request_id']}: instrument_id={instrument_id}, "
            f"raw_symbol={raw_symbol}",
            flush=True,
        )
    return resolved, audit_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument(
        "--key-file",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\databento_api_key.txt"
        ),
    )
    args = parser.parse_args()
    manifest = pd.read_csv(args.manifest, dtype={"resolved_raw_symbol": "string"})
    resolved, audit_rows = resolve_manifest(manifest, args.key_file)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    resolved.to_csv(args.output, index=False)
    audit = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(args.manifest),
        "resolved_manifest": str(args.output),
        "metadata_requests_performed": 2 * len(audit_rows),
        "market_data_downloaded": False,
        "billable_download_performed": False,
        "all_resolved": all(
            row["continuous_to_instrument_status"] == 0
            and row["instrument_to_raw_status"] == 0
            for row in audit_rows
        ),
        "rows": audit_rows,
    }
    args.audit_output.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "resolved_rows": len(audit_rows),
                "all_resolved": audit["all_resolved"],
                "market_data_downloaded": False,
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
