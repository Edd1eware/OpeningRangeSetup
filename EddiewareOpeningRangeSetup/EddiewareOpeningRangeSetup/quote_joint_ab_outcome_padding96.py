"""Quote the 96 pending MBO requests with 100 ms receive-time end padding."""

from __future__ import annotations

import argparse
import json
import shutil
import warnings
from datetime import datetime, timezone
from pathlib import Path

import databento as db
import pandas as pd

from download_databento_mbo_manifest import validate_key
from quote_joint_ab_outcome98 import get_cost_with_retry


LOST_REQUEST_ID = (
    "NQ_JOINT_AB_V4_MBO_2022-04-26_"
    "LB_20220426_093143_SELL_0001"
)


def build_pending_manifest(
    original: pd.DataFrame,
    receipt: dict,
) -> pd.DataFrame:
    mbo = original.loc[original["schema"].eq("mbo")].copy()
    completed = set(receipt.get("rows", {}))
    pending = mbo.loc[~mbo["request_id"].isin(completed)].copy()
    if len(pending) != 96 or LOST_REQUEST_ID not in set(pending["request_id"]):
        raise ValueError("Expected 96 pending rows including the lost third request")
    pending["original_request_id"] = pending["request_id"]
    pending["request_id"] = pending["request_id"] + "_PAD100MS"
    pending["label_end_utc_exclusive"] = pending["end_utc_exclusive"]
    pending["end_utc_exclusive"] = (
        pd.to_datetime(pending["end_utc_exclusive"], utc=True)
        + pd.Timedelta(milliseconds=100)
    ).map(lambda value: value.isoformat())
    pending["request_window_milliseconds"] = 5200
    pending["label_window_milliseconds"] = 5100
    pending["padding_policy"] = "END_TSRECV_PLUS_100MS_NEVER_LABEL"
    return pending.reset_index(drop=True)


def main() -> int:
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    base = project / "contexto_codex_claude" / "joint_ab_v4"
    parser.add_argument(
        "--original-manifest",
        type=Path,
        default=base / "AB_V4_OUTCOME_98_QUOTE_MANIFEST.csv",
    )
    parser.add_argument(
        "--original-costs",
        type=Path,
        default=base / "AB_V4_OUTCOME_98_COST_DETAIL.csv",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=base / "AB_V4_OUTCOME_98_DOWNLOAD_RECEIPT.json",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=base / "AB_V4_OUTCOME_PENDING_96_PAD100_MANIFEST.csv",
    )
    parser.add_argument(
        "--cost-detail",
        type=Path,
        default=base / "AB_V4_OUTCOME_PENDING_96_PAD100_COST.csv",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=base / "AB_V4_OUTCOME_PENDING_96_PAD100_SUMMARY.json",
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

    original = pd.read_csv(args.original_manifest)
    original_costs = pd.read_csv(args.original_costs)
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    pending = build_pending_manifest(original, receipt)
    pending.to_csv(args.manifest_output, index=False)

    if args.cost_detail.exists():
        detail = pd.read_csv(args.cost_detail)
    else:
        detail = pd.DataFrame(
            columns=[
                "request_id",
                "original_request_id",
                "fecha",
                "symbols",
                "start_utc",
                "end_utc_exclusive",
                "estimated_cost_usd",
            ]
        )
    quoted = set(detail["request_id"].astype(str))
    records = detail.to_dict(orient="records")
    client = db.Historical(validate_key(args.key_file))
    for position, row in pending.iterrows():
        request_id = str(row["request_id"])
        if request_id in quoted:
            print(f"[PAD QUOTE {position + 1}/96] cached {row['fecha']}", flush=True)
            continue
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The request time range does not start at UTC midnight.*",
            )
            cost = get_cost_with_retry(client, row)
        records.append(
            {
                "request_id": request_id,
                "original_request_id": str(row["original_request_id"]),
                "fecha": str(row["fecha"]),
                "symbols": str(row["symbols"]),
                "start_utc": str(row["start_utc"]),
                "end_utc_exclusive": str(row["end_utc_exclusive"]),
                "estimated_cost_usd": cost,
            }
        )
        detail = pd.DataFrame(records)
        detail.to_csv(args.cost_detail, index=False)
        quoted.add(request_id)
        print(
            f"[PAD QUOTE {position + 1}/96] {cost:.9f} USD {row['fecha']}",
            flush=True,
        )

    detail = pd.DataFrame(records)
    if set(detail["request_id"]) != set(pending["request_id"]):
        raise RuntimeError("Padding quote is incomplete")
    old_mbo = original_costs.loc[original_costs["schema"].eq("mbo")].copy()
    incurred_ids = set(receipt.get("rows", {})) | {LOST_REQUEST_ID}
    assumed_incurred = float(
        old_mbo.loc[
            old_mbo["request_id"].isin(incurred_ids), "estimated_cost_usd"
        ].sum()
    )
    pending_cost = float(detail["estimated_cost_usd"].sum())
    projected_total = assumed_incurred + pending_cost
    free = shutil.disk_usage(args.manifest_output.parent).free
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "billable_download_started_for_padding": False,
        "completed_valid_old_files": len(receipt.get("rows", {})),
        "lost_old_request_assumed_billed": LOST_REQUEST_ID,
        "assumed_incurred_cost_usd": assumed_incurred,
        "pending_padded_requests": int(len(detail)),
        "pending_padded_cost_usd": pending_cost,
        "projected_worst_case_total_usd": projected_total,
        "additional_authorization_over_old_cap_usd": max(
            0.0, projected_total - 5.76
        ),
        "free_gib": free / 1024**3,
        "reserve_10_gib_pass": free >= 10 * 1024**3,
    }
    args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
