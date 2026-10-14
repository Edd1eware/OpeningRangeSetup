"""ohlcv-1s DBN files -> one tidy parquet per year (ts in ET, prices in ticks).

Downstream code never touches DBN again: bars.parquet is the single source of
truth for price paths, and 1s is fine enough to resolve TP-before-SL inside a
1-minute bar.
"""
from __future__ import annotations

import sys
from pathlib import Path

import databento as db
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA, NY, ROOT
from progress import track

TICK = 0.25          # NQ tick size
POINT_USD = 20.0     # NQ $ per index point -> $5 per tick

SRC = DATA / "ohlcv1s"
OUT = DATA / "bars"


def load_day(path: Path) -> pd.DataFrame:
    store = db.DBNStore.from_file(path)
    df = store.to_df(price_type="float", tz="UTC")
    if df.empty:
        return df
    df = df.reset_index().rename(columns={"ts_event": "ts_utc"})
    df["ts_ny"] = df.ts_utc.dt.tz_convert(NY)
    df["session"] = df.ts_ny.dt.date
    # instrument_id identifies WHICH contract the continuous symbol resolved to.
    # It is the only honest way to spot a roll: the price jumps by the calendar
    # spread there, so any overnight gap measured across it is meaningless.
    keep = ["ts_utc", "ts_ny", "session", "instrument_id",
            "open", "high", "low", "close", "volume"]
    return df[keep]


def main() -> int:
    files = sorted(SRC.glob("NQ_ohlcv-1s_*.dbn.zst"))
    if not files:
        print(f"no files in {SRC}. run 02_download.py --schema ohlcv-1s first.")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    rows = 0
    # Files are named NQ_ohlcv-1s_<date>, so sorting them sorts by date and a
    # year is finished the moment the next one starts. Flushing there keeps one
    # year in memory instead of all of them: with ~1,000 sessions on disk the
    # old all-at-once version held tens of millions of rows before writing
    # anything.
    cur_year: int | None = None
    frames: list[pd.DataFrame] = []

    def flush() -> int:
        nonlocal frames
        if cur_year is None or not frames:
            return 0
        out = pd.concat(frames, ignore_index=True).sort_values("ts_utc")
        out = out.drop_duplicates("ts_utc", keep="last")
        out.to_parquet(OUT / f"bars_1s_{cur_year}.parquet", index=False)
        print(f"  {cur_year}: {len(out):>9,} bars  {out.session.nunique():>4} sessions")
        n = len(out)
        frames = []
        return n

    for f in track(files, label="1s bars -> parquet"):
        df = load_day(f)
        if df.empty:
            continue
        year = int(df.ts_ny.iloc[0].year)
        if cur_year is not None and year != cur_year:
            rows += flush()
        cur_year = year
        frames.append(df)
    rows += flush()
    print(f"total {rows:,} bars -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
