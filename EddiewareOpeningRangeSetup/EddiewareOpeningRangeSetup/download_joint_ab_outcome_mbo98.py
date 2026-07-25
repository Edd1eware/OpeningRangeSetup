"""Download and validate the 98 authorized MBO outcome windows for A/B V4."""

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


AUTHORIZED_CAP_USD = 5.76
FROZEN_QUOTE_USD = 5.755439753831
MIN_FREE_BYTES = 10 * 1024**3
F_LAST = 128
F_MAYBE_BAD_BOOK = 4


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()
    required = {
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
    frame = frame.copy()
    frame["record_ordinal"] = np.arange(len(frame), dtype=np.int64)
    frame["ts_event"] = pd.to_datetime(
        frame["ts_event"], utc=True, errors="raise", format="mixed"
    )
    frame["sequence"] = pd.to_numeric(
        frame["sequence"], errors="raise"
    ).astype("uint64")
    frame["action"] = frame["action"].astype(str)
    frame["side"] = frame["side"].astype(str)
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["size"] = pd.to_numeric(frame["size"], errors="raise").astype("uint64")
    frame["flags"] = pd.to_numeric(
        frame["flags"], errors="raise"
    ).astype("uint16")
    frame["instrument_id"] = pd.to_numeric(
        frame["instrument_id"], errors="raise"
    ).astype("uint32")
    return frame


def last_sales_by_match_event(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    frame = frame.copy()
    frame["is_last"] = (frame["flags"] & F_LAST) != 0
    frame["match_event_id"] = (
        frame["is_last"].shift(fill_value=False).cumsum().astype("int64")
    )
    trades = frame.loc[
        frame["action"].eq("T") & frame["price"].notna()
    ].copy()
    if trades.empty:
        raise ValueError("No T records in MBO window")
    ids = trades["match_event_id"].unique()
    summary = frame.groupby("match_event_id", sort=False).agg(
        closed=("is_last", "any"),
        timestamp_count=("ts_event", "nunique"),
        sequence_count=("sequence", "nunique"),
    )
    used = summary.loc[ids]
    unclosed = int((~used["closed"]).sum())
    mixed_timestamp = int((used["timestamp_count"] != 1).sum())
    if unclosed:
        raise ValueError(f"{unclosed} T Match Events lack F_LAST")
    if mixed_timestamp:
        raise ValueError(f"{mixed_timestamp} T Match Events mix ts_event")
    last_sales = (
        trades.groupby("match_event_id", sort=False)
        .tail(1)
        .sort_values("record_ordinal", kind="mergesort")
        .reset_index(drop=True)
    )
    return last_sales, {
        "t_records": int(len(trades)),
        "t_match_events": int(len(last_sales)),
        "unclosed_t_match_events": unclosed,
        "mixed_timestamp_t_match_events": mixed_timestamp,
        "multi_sequence_t_match_events": int(
            (used["sequence_count"] > 1).sum()
        ),
    }


def inspect_file(path: Path, row: pd.Series) -> dict[str, Any]:
    frame = _normalize(db.DBNStore.from_file(path).to_df())
    if frame.empty:
        raise ValueError(f"Empty MBO file: {path}")
    start = pd.to_datetime(row["start_utc"], utc=True)
    decision = pd.to_datetime(row["decision_utc"], utc=True)
    end = pd.to_datetime(row["end_utc_exclusive"], utc=True)
    if frame["ts_event"].min() < start or frame["ts_event"].max() >= end:
        raise ValueError(f"Records outside authorized interval: {path}")
    maybe_bad = int(((frame["flags"] & F_MAYBE_BAD_BOOK) != 0).sum())
    sequence_regressions = int(
        (
            np.diff(frame["sequence"].astype("int64").to_numpy()) < 0
        ).sum()
    )
    if maybe_bad:
        raise ValueError(f"F_MAYBE_BAD_BOOK={maybe_bad}: {path}")
    if sequence_regressions:
        raise ValueError(
            f"sequence_regressions={sequence_regressions}: {path}"
        )

    last_sales, event_quality = last_sales_by_match_event(frame)
    pre = last_sales.loc[last_sales["ts_event"].lt(decision)]
    post = last_sales.loc[
        last_sales["ts_event"].ge(decision)
        & last_sales["ts_event"].lt(end)
    ]
    if pre.empty or post.empty:
        raise ValueError(
            f"Missing pre/post T-event: pre={len(pre)} post={len(post)}"
        )
    p0 = pre.iloc[-1]
    p0_lag_ms = (decision - p0["ts_event"]).total_seconds() * 1000.0
    if p0_lag_ms < 0 or p0_lag_ms > 100.0:
        raise ValueError(f"p0 outside 100 ms: lag={p0_lag_ms:.6f}")
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
    return {
        "bytes": int(path.stat().st_size),
        "records": int(len(frame)),
        **event_quality,
        "maybe_bad_book_records": maybe_bad,
        "sequence_regressions": sequence_regressions,
        "instrument_ids": instrument_ids,
        "symbols": symbols,
        "ts_event_min": frame["ts_event"].min().isoformat(),
        "ts_event_max": frame["ts_event"].max().isoformat(),
        "p0_ts_event": p0["ts_event"].isoformat(),
        "p0_price": float(p0["price"]),
        "p0_lag_ms": float(p0_lag_ms),
        "post_t_match_events": int(len(post)),
        "last_post_price": float(post.iloc[-1]["price"]),
    }


def download_one(
    client: db.Historical,
    row: pd.Series,
    output_dir: Path,
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
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quote-manifest",
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
        default=project
        / "contexto_codex_claude"
        / "joint_ab_v4"
        / "AB_V4_OUTCOME_98_DOWNLOAD_RECEIPT.json",
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
        "--max-cost-usd", type=float, default=AUTHORIZED_CAP_USD
    )
    args = parser.parse_args()

    manifest = pd.read_csv(args.quote_manifest)
    manifest = manifest.loc[manifest["schema"].eq("mbo")].copy()
    manifest = manifest.sort_values(["fecha", "BurstId"]).reset_index(drop=True)
    costs = pd.read_csv(args.cost_detail)
    costs = costs.loc[costs["schema"].eq("mbo")].copy()
    if len(manifest) != 98 or len(costs) != 98:
        raise ValueError("Expected 98 MBO manifest and cost rows")
    estimated_cost = float(costs["estimated_cost_usd"].sum())
    if abs(estimated_cost - FROZEN_QUOTE_USD) > 1e-9:
        raise ValueError(
            f"Quote changed: {estimated_cost:.12f} != {FROZEN_QUOTE_USD:.12f}"
        )
    if estimated_cost > args.max_cost_usd:
        raise RuntimeError(
            f"Authorized cap exceeded: {estimated_cost:.9f} > "
            f"{args.max_cost_usd:.9f}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    free_before = shutil.disk_usage(args.output_dir).free
    if free_before < MIN_FREE_BYTES:
        raise RuntimeError("10 GiB disk reserve would be violated")
    client = db.Historical(validate_key(args.key_file))
    receipt: dict[str, Any] = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorized_cap_usd": float(args.max_cost_usd),
        "estimated_cost_usd": estimated_cost,
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
                f"Stopped before {row['request_id']}: 10 GiB reserve"
            )
        path, status, validation = download_one(client, row, args.output_dir)
        receipt["rows"][str(row["request_id"])] = {
            "status": status,
            "path": str(path),
            "estimated_cost_usd": float(
                costs.loc[
                    costs["request_id"].eq(row["request_id"]),
                    "estimated_cost_usd",
                ].iloc[0]
            ),
            **validation,
        }
        args.receipt.write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )
        print(
            f"[DOWNLOAD {position + 1}/98] {row['fecha']} {status} "
            f"records={validation['records']} "
            f"T-events={validation['t_match_events']} "
            f"p0lag={validation['p0_lag_ms']:.3f}ms",
            flush=True,
        )

    if len(receipt["rows"]) != 98:
        raise RuntimeError("Receipt incomplete after download loop")
    free_after = shutil.disk_usage(args.output_dir).free
    receipt.update(
        {
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "completed_sessions": 98,
            "total_bytes": int(
                sum(int(item["bytes"]) for item in receipt["rows"].values())
            ),
            "free_bytes_after": int(free_after),
            "reserve_10_gib_pass": free_after >= MIN_FREE_BYTES,
            "integrity_pass": all(
                int(item["unclosed_t_match_events"]) == 0
                and int(item["mixed_timestamp_t_match_events"]) == 0
                and int(item["maybe_bad_book_records"]) == 0
                and int(item["sequence_regressions"]) == 0
                for item in receipt["rows"].values()
            ),
        }
    )
    args.receipt.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
