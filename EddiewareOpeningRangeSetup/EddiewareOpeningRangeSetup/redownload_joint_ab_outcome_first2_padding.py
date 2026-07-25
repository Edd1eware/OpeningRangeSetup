"""Redownload only the first two joint A/B V4 outcomes with end padding."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
import pandas as pd

from download_databento_mbo_manifest import validate_key
from download_joint_ab_outcome_padding96 import (
    MIN_FREE_BYTES,
    download_one,
)


AUTHORIZED_TOTAL_CAP_USD = 5.93
PRIOR_WORST_CASE_USD = 5.810737153888001
ADDITIONAL_QUOTE_USD = 0.111598911882
NEW_WORST_CASE_USD = PRIOR_WORST_CASE_USD + ADDITIONAL_QUOTE_USD
TARGET_IDS = {
    "NQ_JOINT_AB_V4_MBO_2022-04-05_LB_20220405_093200_BUY_0001",
    "NQ_JOINT_AB_V4_MBO_2022-04-06_LB_20220406_093100_BUY_0001",
}
COSTS = {
    "NQ_JOINT_AB_V4_MBO_2022-04-05_LB_20220405_093200_BUY_0001_PAD100MS":
        0.050874182582,
    "NQ_JOINT_AB_V4_MBO_2022-04-06_LB_20220406_093100_BUY_0001_PAD100MS":
        0.060724729300,
}


def build_manifest(original: pd.DataFrame) -> pd.DataFrame:
    selected = original.loc[
        original["schema"].eq("mbo")
        & original["request_id"].isin(TARGET_IDS)
    ].copy()
    if len(selected) != 2:
        raise ValueError("Expected the two frozen first-session requests")
    selected["original_request_id"] = selected["request_id"]
    selected["request_id"] = selected["request_id"] + "_PAD100MS"
    selected["label_end_utc_exclusive"] = selected["end_utc_exclusive"]
    selected["end_utc_exclusive"] = (
        pd.to_datetime(selected["end_utc_exclusive"], utc=True)
        + pd.Timedelta(milliseconds=100)
    ).map(lambda value: value.isoformat())
    selected["request_window_milliseconds"] = 5200
    selected["label_window_milliseconds"] = 5100
    selected["padding_policy"] = "END_TSRECV_PLUS_100MS_NEVER_LABEL"
    return selected.sort_values("fecha").reset_index(drop=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    project = Path(__file__).resolve().parent
    base = project / "contexto_codex_claude" / "joint_ab_v4"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--original-manifest",
        type=Path,
        default=base / "AB_V4_OUTCOME_98_QUOTE_MANIFEST.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
            r"\databento_mbo\joint_ab_v4_outcome98_20260724"
        ),
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=base / "AB_V4_OUTCOME_FIRST2_PAD100_RECEIPT.json",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=base / "AB_V4_OUTCOME_FIRST2_PAD100_MANIFEST.csv",
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
        "--max-total-cost-usd",
        type=float,
        default=AUTHORIZED_TOTAL_CAP_USD,
    )
    args = parser.parse_args()

    if NEW_WORST_CASE_USD > args.max_total_cost_usd:
        raise RuntimeError(
            f"Authorized cap exceeded: {NEW_WORST_CASE_USD:.12f} > "
            f"{args.max_total_cost_usd:.12f}"
        )
    manifest = build_manifest(pd.read_csv(args.original_manifest))
    if abs(sum(COSTS.values()) - ADDITIONAL_QUOTE_USD) > 1e-12:
        raise ValueError("Frozen two-window cost sum differs")
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(args.manifest_output, index=False)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.output_dir).free < MIN_FREE_BYTES:
        raise RuntimeError("10 GiB disk reserve would be violated")

    client = db.Historical(validate_key(args.key_file))
    receipt: dict[str, Any] = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorized_total_cap_usd": float(args.max_total_cost_usd),
        "additional_quote_usd": ADDITIONAL_QUOTE_USD,
        "new_worst_case_total_usd": NEW_WORST_CASE_USD,
        "rows": {},
    }
    quarantine = args.output_dir / "quarantine"
    for position, row in manifest.iterrows():
        if shutil.disk_usage(args.output_dir).free < MIN_FREE_BYTES:
            raise RuntimeError("10 GiB disk reserve would be violated")
        path, status, validation = download_one(
            client, row, args.output_dir, quarantine
        )
        original = args.output_dir / (
            f"{row['original_request_id']}.mbo.dbn.zst"
        )
        if not original.exists():
            raise FileNotFoundError(f"Missing legacy file: {original}")
        receipt["rows"][str(row["request_id"])] = {
            "status": status,
            "path": str(path),
            "sha256": _sha256(path),
            "legacy_path": str(original),
            "legacy_sha256": _sha256(original),
            "estimated_cost_usd": COSTS[str(row["request_id"])],
            **validation,
        }
        args.receipt.write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )
        print(
            f"[FIRST2 PAD {position + 1}/2] {row['fecha']} {status} "
            f"records={validation['records']} "
            f"padding={validation['transport_padding_records_never_labeled']}",
            flush=True,
        )
    free_after = shutil.disk_usage(args.output_dir).free
    receipt.update(
        {
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "valid_sessions": len(receipt["rows"]),
            "free_bytes_after": int(free_after),
            "reserve_10_gib_pass": free_after >= MIN_FREE_BYTES,
            "integrity_pass": len(receipt["rows"]) == 2,
        }
    )
    args.receipt.write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in receipt.items() if key != "rows"},
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
