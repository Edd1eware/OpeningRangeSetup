"""Download the 96 authorized padded MBO outcome windows for joint A/B V4.

The Historical API request is bounded in receive time (ts_recv).  Causal
outcomes remain bounded in exchange time (ts_event); the final 100 ms is
transport padding only and is never eligible for a label.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import databento as db
import numpy as np
import pandas as pd

from download_databento_mbo_manifest import validate_key


AUTHORIZED_CAP_USD = 5.82
ASSUMED_INCURRED_USD = 0.166896311939
FROZEN_PENDING_QUOTE_USD = 5.643840841949
FROZEN_WORST_CASE_USD = ASSUMED_INCURRED_USD + FROZEN_PENDING_QUOTE_USD
MIN_FREE_BYTES = 10 * 1024**3
F_LAST = 128
F_MAYBE_BAD_BOOK = 4


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    required = {
        "ts_recv",
        "ts_event",
        "sequence",
        "action",
        "side",
        "price",
        "size",
        "flags",
        "instrument_id",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"MBO file lacks fields: {sorted(missing)}")
    result = frame.copy()
    result["record_ordinal"] = np.arange(len(result), dtype=np.int64)
    for field in ("ts_recv", "ts_event"):
        result[field] = pd.to_datetime(
            result[field], utc=True, errors="raise", format="mixed"
        )
    result["sequence"] = pd.to_numeric(
        result["sequence"], errors="raise"
    ).astype("uint64")
    result["action"] = result["action"].astype(str)
    result["side"] = result["side"].astype(str)
    result["price"] = pd.to_numeric(result["price"], errors="coerce")
    result["size"] = pd.to_numeric(
        result["size"], errors="raise"
    ).astype("uint64")
    result["flags"] = pd.to_numeric(
        result["flags"], errors="raise"
    ).astype("uint16")
    result["instrument_id"] = pd.to_numeric(
        result["instrument_id"], errors="raise"
    ).astype("uint32")
    return result


def _match_event_tables(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    marked = frame.copy()
    marked["is_last"] = (marked["flags"] & F_LAST) != 0
    marked["match_event_id"] = (
        marked["is_last"].shift(fill_value=False).cumsum().astype("int64")
    )
    summary = marked.groupby("match_event_id", sort=False).agg(
        closed=("is_last", "any"),
        timestamp_count=("ts_event", "nunique"),
        sequence_count=("sequence", "nunique"),
        first_ordinal=("record_ordinal", "min"),
        last_ordinal=("record_ordinal", "max"),
    )
    trades = marked.loc[
        marked["action"].eq("T") & marked["price"].notna()
    ].copy()
    if trades.empty:
        raise ValueError("No T records in MBO window")
    last_sales = (
        trades.groupby("match_event_id", sort=False)
        .tail(1)
        .sort_values("record_ordinal", kind="mergesort")
        .reset_index(drop=True)
    )
    return last_sales, summary


def inspect_file(path: Path, row: pd.Series) -> dict[str, Any]:
    frame = _normalize(db.DBNStore.from_file(path).to_df())
    if frame.empty:
        raise ValueError(f"Empty MBO file: {path}")

    request_start = pd.to_datetime(row["start_utc"], utc=True)
    decision = pd.to_datetime(row["decision_utc"], utc=True)
    label_end = pd.to_datetime(row["label_end_utc_exclusive"], utc=True)
    request_end = pd.to_datetime(row["end_utc_exclusive"], utc=True)
    if request_start != decision - pd.Timedelta(milliseconds=100):
        raise ValueError("Request start is not decision - 100 ms")
    if label_end != decision + pd.Timedelta(seconds=5):
        raise ValueError("Label end is not decision + 5 s")
    if request_end != label_end + pd.Timedelta(milliseconds=100):
        raise ValueError("Request end is not label end + 100 ms")

    # Databento Historical bounds MBO ranges on ts_recv.  ts_event may legally
    # precede request_start because exchange time precedes receive time.
    if frame["ts_recv"].min() < request_start:
        raise ValueError(f"ts_recv before request start: {path}")
    if frame["ts_recv"].max() >= request_end:
        raise ValueError(f"ts_recv at/after request end: {path}")

    maybe_bad = int(((frame["flags"] & F_MAYBE_BAD_BOOK) != 0).sum())
    sequence_regressions = int(
        (np.diff(frame["sequence"].astype("int64").to_numpy()) < 0).sum()
    )
    if maybe_bad:
        raise ValueError(f"F_MAYBE_BAD_BOOK={maybe_bad}: {path}")
    if sequence_regressions:
        raise ValueError(
            f"sequence_regressions={sequence_regressions}: {path}"
        )

    last_sales, summary = _match_event_tables(frame)
    p0_candidates = last_sales.loc[
        last_sales["ts_event"].ge(decision - pd.Timedelta(milliseconds=100))
        & last_sales["ts_event"].lt(decision)
    ]
    post = last_sales.loc[
        last_sales["ts_event"].ge(decision)
        & last_sales["ts_event"].lt(label_end)
    ]
    if p0_candidates.empty or post.empty:
        raise ValueError(
            "Missing causal T-event: "
            f"p0_candidates={len(p0_candidates)} post={len(post)}"
        )
    p0 = p0_candidates.iloc[-1]
    used_ids = pd.Index(
        [int(p0["match_event_id"])]
        + [int(value) for value in post["match_event_id"]]
    ).unique()
    used_quality = summary.loc[used_ids]
    unclosed = int((~used_quality["closed"]).sum())
    mixed_timestamp = int(
        (used_quality["timestamp_count"] != 1).sum()
    )
    if unclosed:
        raise ValueError(f"{unclosed} used T Match Events lack F_LAST")
    if mixed_timestamp:
        raise ValueError(
            f"{mixed_timestamp} used T Match Events mix ts_event"
        )

    p0_lag_ms = (decision - p0["ts_event"]).total_seconds() * 1000.0
    if not 0.0 < p0_lag_ms <= 100.0:
        raise ValueError(f"p0 outside prior 100 ms: lag={p0_lag_ms:.6f}")
    instrument_ids = sorted(
        int(value) for value in frame["instrument_id"].unique()
    )
    if len(instrument_ids) != 1:
        raise ValueError(f"Expected one instrument_id, got {instrument_ids}")
    symbols = (
        sorted(str(value) for value in frame["symbol"].dropna().unique())
        if "symbol" in frame.columns
        else []
    )
    if symbols and symbols != [str(row["symbols"])]:
        raise ValueError(
            f"Symbol mismatch: requested={row['symbols']} file={symbols}"
        )

    padding_records = int(
        frame["ts_event"].ge(label_end).sum()
    )
    return {
        "bytes": int(path.stat().st_size),
        "records": int(len(frame)),
        "t_records": int(frame["action"].eq("T").sum()),
        "t_match_events": int(len(last_sales)),
        "used_t_match_events": int(len(used_ids)),
        "unclosed_used_t_match_events": unclosed,
        "mixed_timestamp_used_t_match_events": mixed_timestamp,
        "multi_sequence_used_t_match_events": int(
            (used_quality["sequence_count"] > 1).sum()
        ),
        "maybe_bad_book_records": maybe_bad,
        "sequence_regressions": sequence_regressions,
        "instrument_ids": instrument_ids,
        "symbols": symbols,
        "ts_recv_min": frame["ts_recv"].min().isoformat(),
        "ts_recv_max": frame["ts_recv"].max().isoformat(),
        "ts_event_min": frame["ts_event"].min().isoformat(),
        "ts_event_max": frame["ts_event"].max().isoformat(),
        "p0_ts_event": p0["ts_event"].isoformat(),
        "p0_price": float(p0["price"]),
        "p0_lag_ms": float(p0_lag_ms),
        "post_t_match_events": int(len(post)),
        "last_post_price": float(post.iloc[-1]["price"]),
        "transport_padding_records_never_labeled": padding_records,
        "information_status": "OUTCOME_ONLY_NEVER_PREDICTOR",
    }


def download_one(
    client: db.Historical,
    row: pd.Series,
    output_dir: Path,
    quarantine_dir: Path,
) -> tuple[Path, str, dict[str, Any]]:
    final = output_dir / f"{row['request_id']}.mbo.dbn.zst"
    if final.exists():
        return final, "existing_valid", inspect_file(final, row)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{row['request_id']}.",
        suffix=".mbo.dbn.zst",
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
                schema="mbo",
                start=str(row["start_utc"]),
                end=str(row["end_utc_exclusive"]),
                stype_in=str(row["stype_in"]),
                stype_out=str(row["stype_out"]),
            )
        store.to_file(temporary)
        validation = inspect_file(temporary, row)
        temporary.replace(final)
        return final, "downloaded", validation
    except Exception:
        # Never delete a potentially billable response.  Preserve it for
        # diagnosis and prevent an accidental duplicate request.
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        quarantine = quarantine_dir / (
            f"{row['request_id']}.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            ".mbo.dbn.zst"
        )
        if temporary.exists():
            temporary.replace(quarantine)
        raise


def main() -> int:
    project = Path(__file__).resolve().parent
    base = project / "contexto_codex_claude" / "joint_ab_v4"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
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
        default=base / "AB_V4_OUTCOME_PENDING_96_PAD100_RECEIPT.json",
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
        default=AUTHORIZED_CAP_USD,
    )
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest)
    costs = pd.read_csv(args.cost_detail)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    if len(manifest) != 96 or len(costs) != 96:
        raise ValueError("Expected 96 padded manifest and cost rows")
    if set(manifest["request_id"]) != set(costs["request_id"]):
        raise ValueError("Manifest/cost request IDs differ")
    pending_cost = float(costs["estimated_cost_usd"].sum())
    if abs(pending_cost - FROZEN_PENDING_QUOTE_USD) > 1e-9:
        raise ValueError(
            f"Quote changed: {pending_cost:.12f} != "
            f"{FROZEN_PENDING_QUOTE_USD:.12f}"
        )
    projected_total = ASSUMED_INCURRED_USD + pending_cost
    if abs(
        projected_total
        - float(summary["projected_worst_case_total_usd"])
    ) > 1e-9:
        raise ValueError("Frozen cost summary differs")
    if projected_total > args.max_total_cost_usd:
        raise RuntimeError(
            f"Authorized cap exceeded: {projected_total:.9f} > "
            f"{args.max_total_cost_usd:.9f}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir = args.output_dir / "quarantine"
    free_before = shutil.disk_usage(args.output_dir).free
    if free_before < MIN_FREE_BYTES:
        raise RuntimeError("10 GiB disk reserve would be violated")
    client = db.Historical(validate_key(args.key_file))
    receipt: dict[str, Any] = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorized_cap_usd": float(args.max_total_cost_usd),
        "assumed_incurred_cost_usd": ASSUMED_INCURRED_USD,
        "pending_estimated_cost_usd": pending_cost,
        "projected_worst_case_total_usd": projected_total,
        "free_bytes_before": int(free_before),
        "rows": {},
    }
    if args.receipt.exists():
        prior = json.loads(args.receipt.read_text(encoding="utf-8"))
        if isinstance(prior.get("rows"), dict):
            receipt["rows"] = prior["rows"]

    cost_by_id = costs.set_index("request_id")["estimated_cost_usd"]
    failures = []
    for position, row in manifest.iterrows():
        request_id = str(row["request_id"])
        if (
            request_id in receipt["rows"]
            and receipt["rows"][request_id].get("status")
            in {"downloaded", "existing_valid"}
        ):
            print(
                f"[PAD DOWNLOAD {position + 1}/96] cached {row['fecha']}",
                flush=True,
            )
            continue
        free_now = shutil.disk_usage(args.output_dir).free
        if free_now < MIN_FREE_BYTES:
            raise RuntimeError(
                f"Stopped before {request_id}: 10 GiB reserve"
            )
        try:
            path, status, validation = download_one(
                client, row, args.output_dir, quarantine_dir
            )
            receipt["rows"][request_id] = {
                "status": status,
                "path": str(path),
                "estimated_cost_usd": float(cost_by_id.loc[request_id]),
                **validation,
            }
            print(
                f"[PAD DOWNLOAD {position + 1}/96] {row['fecha']} {status} "
                f"records={validation['records']} "
                f"T-events={validation['t_match_events']} "
                f"p0lag={validation['p0_lag_ms']:.3f}ms "
                f"padding={validation['transport_padding_records_never_labeled']}",
                flush=True,
            )
        except Exception as error:
            failures.append({"request_id": request_id, "error": repr(error)})
            receipt["rows"][request_id] = {
                "status": "quarantined_invalid",
                "estimated_cost_usd": float(cost_by_id.loc[request_id]),
                "error": repr(error),
            }
            print(
                f"[PAD DOWNLOAD {position + 1}/96] QUARANTINED "
                f"{row['fecha']}: {error!r}",
                flush=True,
            )
        args.receipt.write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )

    valid = [
        item
        for item in receipt["rows"].values()
        if item.get("status") in {"downloaded", "existing_valid"}
    ]
    free_after = shutil.disk_usage(args.output_dir).free
    receipt.update(
        {
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "valid_sessions": len(valid),
            "quarantined_sessions": len(failures),
            "failures": failures,
            "total_valid_bytes": int(
                sum(int(item["bytes"]) for item in valid)
            ),
            "free_bytes_after": int(free_after),
            "reserve_10_gib_pass": free_after >= MIN_FREE_BYTES,
            "integrity_pass": len(valid) == 96 and not failures,
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
    return 0 if receipt["integrity_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
