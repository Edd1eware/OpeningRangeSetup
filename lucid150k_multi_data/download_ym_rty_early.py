"""Resumable bounded YM+RTY acquisition for preregistered V4 breadth."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import databento as db
import pandas as pd

BASE = Path(__file__).resolve().parent
NQ_ROOT = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
    r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_2"
)
KEY_PATH = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
    r"\databento_api_key.txt"
)
DATA_ROOT = BASE / "combined_early"
MANIFEST = BASE / "DOWNLOAD_MANIFEST.json"
QUOTE = BASE / "QUOTE_SAMPLE_YM_RTY.json"
NY = ZoneInfo("America/New_York")

DATASET = "GLBX.MDP3"
SYMBOLS = ["YM.c.0", "RTY.c.0"]
SCHEMA = "ohlcv-1s"
STYPE = "continuous"
DATE_START = "2022-04-25"
DATE_END = "2026-06-30"
SPECIFIC_CAP_BYTES = 5 * 1024**3
MIN_FREE_BYTES = 25 * 1024**3


def bounds(date: str) -> tuple[str, str]:
    start = pd.Timestamp(f"{date} 09:25:00", tz=NY).tz_convert("UTC")
    end = pd.Timestamp(f"{date} 10:05:00", tz=NY).tz_convert("UTC")
    return start.isoformat(), end.isoformat()


def final_path(date: str) -> Path:
    return DATA_ROOT / date / SCHEMA / "ym_rty.dbn.zst"


def folder_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def write_manifest(payload: dict) -> None:
    temporary = MANIFEST.with_suffix(".json.partial")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, MANIFEST)


def fetch_one(api_key: str, date: str, output: Path) -> int:
    start, end = bounds(date)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name("ym_rty.partial.dbn.zst")
    if temporary.exists():
        temporary.unlink()
    client = db.Historical(api_key)
    for attempt in range(8):
        try:
            store = client.timeseries.get_range(
                dataset=DATASET,
                symbols=SYMBOLS,
                schema=SCHEMA,
                start=start,
                end=end,
                stype_in=STYPE,
            )
            store.to_file(temporary)
            size = temporary.stat().st_size
            if size < 1_000:
                raise ValueError("DBN response is smaller than a valid payload")
            os.replace(temporary, output)
            return size
        except Exception:
            if temporary.exists():
                temporary.unlink()
            if attempt == 7:
                raise
            time.sleep(min(2 * (attempt + 1), 15))
    raise RuntimeError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum missing sessions to fetch; 0 means all.",
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    quote = json.loads(QUOTE.read_text(encoding="utf-8"))
    if quote["projected_total_usd_with_25pct_margin"] > 25.0:
        raise SystemExit("Projected quote exceeds frozen USD 25 safety ceiling")

    dates = sorted(
        path.name for path in NQ_ROOT.iterdir()
        if path.is_dir() and DATE_START <= path.name <= DATE_END
    )
    missing = [date for date in dates if not final_path(date).exists()]
    if args.limit > 0:
        missing = missing[: args.limit]
    api_key = KEY_PATH.read_text(encoding="utf-8").strip()
    initial_bytes = folder_bytes(DATA_ROOT)
    completed_now = 0
    errors = []

    if folder_bytes(DATA_ROOT) >= SPECIFIC_CAP_BYTES:
        raise SystemExit("V4 5 GB data cap reached")
    if shutil.disk_usage(BASE.anchor).free < MIN_FREE_BYTES:
        raise SystemExit("C: free space fell below 25 GB reserve")

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(args.workers, 4))
    ) as executor:
        pending = {
            executor.submit(fetch_one, api_key, date, final_path(date)): date
            for date in missing
        }
        for index, future in enumerate(
            concurrent.futures.as_completed(pending), start=1
        ):
            date = pending[future]
            try:
                size = future.result()
                completed_now += 1
                print(
                    f"[{index:4d}/{len(missing)}] {date} "
                    f"bytes={size} "
                    f"total_mb={folder_bytes(DATA_ROOT)/1024**2:.2f}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"date": date, "error": repr(exc)})
                print(f"ERROR {date}: {exc!r}", flush=True)
            current_bytes = folder_bytes(DATA_ROOT)
            free_bytes = shutil.disk_usage(BASE.anchor).free
            if current_bytes >= SPECIFIC_CAP_BYTES:
                raise SystemExit("V4 5 GB data cap reached")
            if free_bytes < MIN_FREE_BYTES:
                raise SystemExit("C: free space fell below 25 GB reserve")
            payload = {
                "updated_utc": datetime.now(timezone.utc).isoformat(),
                "dataset": DATASET,
                "symbols": SYMBOLS,
                "schema": SCHEMA,
                "window_ny": "09:25:00..10:05:00",
                "date_range": [DATE_START, DATE_END],
                "expected_sessions": len(dates),
                "files_complete": sum(
                    final_path(date).exists() for date in dates
                ),
                "completed_this_run": completed_now,
                "errors_this_run": errors,
                "bytes_total": current_bytes,
                "bytes_added_this_run": current_bytes - initial_bytes,
                "cap_bytes": SPECIFIC_CAP_BYTES,
                "free_bytes": free_bytes,
                "projected_cost_usd": quote["projected_total_usd_mean"],
                "projected_cost_with_margin_usd": quote[
                    "projected_total_usd_with_25pct_margin"
                ],
            }
            write_manifest(payload)

    print(json.dumps(payload, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
