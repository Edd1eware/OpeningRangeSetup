"""
Cache NQ RTH 1-second bars as one compressed npz so the throughput census can
sweep hundreds of parameter combinations without paying DBN decompression on
every pass.

Stores prices already converted to integer ticks (NQ tick = 0.25) to keep the
comparisons exact and the arrays small.
"""

import glob
import os
import time

import numpy as np
import databento as db

from progress import track

SRC = r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR\data\raw_dbn_2"
OUT = "nq_1s_cache.npz"
TICK = 0.25


def main():
    t0 = time.time()
    days = sorted(d for d in os.listdir(SRC) if d[0].isdigit())
    print(f"days found: {len(days)}  [{days[0]} .. {days[-1]}]")

    closes, highs, lows, vols, secs = [], [], [], [], []
    offsets = [0]
    kept = []

    for day in track(days, label="cache 1s bars"):
        files = glob.glob(os.path.join(SRC, day, "ohlcv-1s-full", "*.dbn.zst"))
        if not files:
            continue
        try:
            df = db.DBNStore.from_file(files[0]).to_df()
        except Exception:
            continue
        if df.empty:
            continue
        # seconds since 00:00 UTC; DST is handled downstream by using the
        # session's own first bar as the open reference
        ts = df.index
        sec = (ts.hour * 3600 + ts.minute * 60 + ts.second).to_numpy(np.int32)
        closes.append(np.rint(df["close"].to_numpy() / TICK).astype(np.int32))
        highs.append(np.rint(df["high"].to_numpy() / TICK).astype(np.int32))
        lows.append(np.rint(df["low"].to_numpy() / TICK).astype(np.int32))
        vols.append(df["volume"].to_numpy().astype(np.int32))
        secs.append(sec)
        offsets.append(offsets[-1] + len(df))
        kept.append(day)

    np.savez_compressed(
        OUT,
        close=np.concatenate(closes),
        high=np.concatenate(highs),
        low=np.concatenate(lows),
        volume=np.concatenate(vols),
        sec=np.concatenate(secs),
        offsets=np.array(offsets, dtype=np.int64),
        days=np.array(kept),
    )
    size_mb = os.path.getsize(OUT) / 1e6
    print(f"\ncached {len(kept)} days, {offsets[-1]:,} bars, {size_mb:.1f} MB "
          f"[{time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
