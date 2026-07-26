"""Resumable bounded NQ+ES overnight 1-minute acquisition for V14."""

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
DATA_ROOT = BASE / "data_overnight_1m"
MANIFEST = BASE / "DOWNLOAD_MANIFEST.json"
QUOTE = BASE / "QUOTE_NQ_ES_OVERNIGHT_1M.json"
NY = ZoneInfo("America/New_York")
DATASET = "GLBX.MDP3"
SYMBOLS = ["NQ.c.0", "ES.c.0"]
SCHEMA = "ohlcv-1m"
STYPE = "continuous"
DATE_START = "2022-04-25"
DATE_END = "2026-06-30"
SPECIFIC_CAP_BYTES = 2 * 1024**3
MIN_FREE_BYTES = 25 * 1024**3
MAX_QUOTE_USD_WITH_MARGIN = 10.0


def bounds(date: str) -> tuple[str, str]:
    current = pd.Timestamp(date, tz=NY)
    start = current - pd.Timedelta(days=1) + pd.Timedelta(hours=18)
    end = current + pd.Timedelta(hours=9, minutes=30)
    return start.tz_convert("UTC").isoformat(), end.tz_convert("UTC").isoformat()


def final_path(date: str) -> Path:
    return DATA_ROOT / date / SCHEMA / "nq_es_overnight.dbn.zst"


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
    temporary = output.with_name("nq_es_overnight.partial.dbn.zst")
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
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    quote = json.loads(QUOTE.read_text(encoding="utf-8"))
    if quote["projected_total_usd_with_25pct_margin"] > MAX_QUOTE_USD_WITH_MARGIN:
        raise SystemExit("Projected quote exceeds frozen USD 10 safety ceiling")
    dates = sorted(
        path.name
        for path in NQ_ROOT.iterdir()
        if path.is_dir() and DATE_START <= path.name <= DATE_END
    )
    missing = [date for date in dates if not final_path(date).exists()]
    if args.limit > 0:
        missing = missing[: args.limit]
    api_key = KEY_PATH.read_text(encoding="utf-8").strip()
    initial_bytes = folder_bytes(DATA_ROOT)
    completed_now = 0
    errors = []
    if initial_bytes >= SPECIFIC_CAP_BYTES:
        raise SystemExit("V14 2 GB data cap reached")
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
                    f"[{index:4d}/{len(missing)}] {date} bytes={size} "
                    f"total_mb={folder_bytes(DATA_ROOT)/1024**2:.2f}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"date": date, "error": repr(exc)})
                print(f"ERROR {date}: {exc!r}", flush=True)
            current_bytes = folder_bytes(DATA_ROOT)
            free_bytes = shutil.disk_usage(BASE.anchor).free
            if current_bytes >= SPECIFIC_CAP_BYTES:
                raise SystemExit("V14 2 GB data cap reached")
            if free_bytes < MIN_FREE_BYTES:
                raise SystemExit("C: free space fell below 25 GB reserve")
            write_manifest(
                {
                    "updated_utc": datetime.now(timezone.utc).isoformat(),
                    "dates_total": len(dates),
                    "missing_at_start": len(missing),
                    "completed_now": completed_now,
                    "errors": errors,
                    "data_bytes": current_bytes,
                    "free_bytes": free_bytes,
                }
            )
    print(
        json.dumps(
            {
                "completed_now": completed_now,
                "errors": len(errors),
                "data_bytes_added": folder_bytes(DATA_ROOT) - initial_bytes,
                "data_bytes_total": folder_bytes(DATA_ROOT),
            },
            indent=2,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
