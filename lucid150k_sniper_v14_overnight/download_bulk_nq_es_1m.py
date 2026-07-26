"""One-request NQ+ES 1-minute download, later filtered to V14 windows."""

import os
import shutil
from pathlib import Path

import databento as db

BASE = Path(__file__).resolve().parent
KEY_PATH = Path(
    r"C:\Users\k_99_\Desktop\codding\data_footprint_generator"
    r"\databento_api_key.txt"
)
OUTPUT = BASE / "nq_es_1m_20220424_20260630.dbn.zst"
PARTIAL = OUTPUT.with_suffix(".partial.dbn.zst")
MAX_BYTES = 2 * 1024**3
MIN_FREE_BYTES = 25 * 1024**3
FROZEN_QUOTE_USD = 10.7276
MAX_COST_USD = 12.0

if FROZEN_QUOTE_USD > MAX_COST_USD:
    raise SystemExit("Bulk quote exceeds USD 12 safety ceiling")
if shutil.disk_usage(BASE.anchor).free < MIN_FREE_BYTES:
    raise SystemExit("C: free space fell below 25 GB reserve")
if OUTPUT.exists():
    print(f"ALREADY_COMPLETE bytes={OUTPUT.stat().st_size}")
    raise SystemExit(0)
if PARTIAL.exists():
    PARTIAL.unlink()

client = db.Historical(KEY_PATH.read_text(encoding="utf-8").strip())
store = client.timeseries.get_range(
    dataset="GLBX.MDP3",
    symbols=["NQ.c.0", "ES.c.0"],
    schema="ohlcv-1m",
    start="2022-04-24T22:00:00Z",
    end="2026-06-30T13:30:00Z",
    stype_in="continuous",
)
store.to_file(PARTIAL)
size = PARTIAL.stat().st_size
if size < 1_000 or size > MAX_BYTES:
    raise SystemExit(f"Invalid output size: {size}")
if shutil.disk_usage(BASE.anchor).free < MIN_FREE_BYTES:
    raise SystemExit("C: free space fell below 25 GB reserve")
os.replace(PARTIAL, OUTPUT)
print(f"DOWNLOAD_COMPLETE bytes={size} quote_usd={FROZEN_QUOTE_USD}")
