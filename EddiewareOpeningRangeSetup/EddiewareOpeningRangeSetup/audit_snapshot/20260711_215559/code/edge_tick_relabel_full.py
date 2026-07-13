"""Exact MBO relabel for all 486 sessions, at the declared OR-edge entry."""

from __future__ import annotations

import csv
import glob
import pickle
import time
from pathlib import Path

import databento as db
import duckdb
import numpy as np


BASE = Path(__file__).resolve().parent
OUT = BASE / "outputs" / "edge_validation_20260630"
DB_PATH = OUT / "orb_features_snapshot.duckdb"
ROOT = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR")
RAW = ROOT / "data" / "raw_dbn"
SCRATCH = Path(
    r"C:\Users\k_99_\AppData\Local\Temp\claude"
    r"\C--Users-k-99--Desktop\59a5d941-0bcb-4a83-9f25-1c27f99384b9\scratchpad"
)
FULL_PATH = SCRATCH / "full_mbo.pkl"
OUT_PATH = OUT / "tick_labels_486.csv"


def fade_label(mbo_path: str, breakout_ns: int, cutoff_ns: int, entry: float, long: bool):
    tp = entry + 7.5 if long else entry - 7.5
    sl = entry - 7.5 if long else entry + 7.5
    first_recv = None
    used = 0
    store = db.DBNStore.from_file(mbo_path)
    for chunk in store.to_ndarray(count=500_000):
        recv = chunk["ts_recv"]
        if len(recv) == 0 or recv[-1] < breakout_ns:
            continue
        if recv[0] > cutoff_ns:
            break
        trades = chunk[
            (chunk["action"] == b"T")
            & (recv >= breakout_ns)
            & (recv <= cutoff_ns)
        ]
        if len(trades) == 0:
            continue
        if first_recv is None:
            first_recv = int(trades["ts_recv"][0])
        prices = trades["price"].astype("float64") / 1_000_000_000
        if long:
            hit = (prices >= tp) | (prices <= sl)
        else:
            hit = (prices <= tp) | (prices >= sl)
        loc = np.flatnonzero(hit)
        if len(loc):
            idx = int(loc[0])
            used += idx + 1
            if long:
                outcome = int(prices[idx] >= tp)
            else:
                outcome = int(prices[idx] <= tp)
            return outcome, int(trades["ts_recv"][idx]), first_recv, used
        used += len(trades)
    return None, None, first_recv, used


def main() -> None:
    with FULL_PATH.open("rb") as handle:
        full = pickle.load(handle)
    source = {str(row["date"]): row for row in full}
    con = duckdb.connect(str(DB_PATH), read_only=True)
    rows = con.execute(
        """
        SELECT CAST(b.session_date AS VARCHAR), b.breakout_ts, b.direction,
               l.entry_price, ol.locked_ts, ol.or_low * .25, ol.or_high * .25
        FROM breakout_features b
        JOIN labels l USING(session_date)
        JOIN or_levels ol USING(session_date)
        ORDER BY b.session_date
        """
    ).fetchall()
    con.close()

    metadata = {}
    for date, breakout, direction, prior_entry, locked, low, high in rows:
        if date not in source:
            continue
        edge = float(low if direction == "DOWN" else high)
        metadata[date] = dict(
            breakout=int(breakout), direction=direction,
            prior_entry=float(prior_entry), entry=edge, locked=int(locked),
        )

    results = []
    started = time.time()
    for i, date in enumerate(sorted(source), start=1):
        src = source[date]
        meta = metadata[date]
        matches = glob.glob(str(RAW / date / "mbo" / "*.zst"))
        if not matches:
            y_fade = exit_ns = first_ns = None
            used = 0
            status = "NO_MBO"
        else:
            y_fade, exit_ns, first_ns, used = fade_label(
                matches[0], meta["breakout"], meta["locked"] + 19 * 60 * 1_000_000_000,
                meta["entry"], long=(meta["direction"] == "DOWN"),
            )
            status = "OK" if y_fade is not None else "NO_TOUCH"
        y_cont = None if y_fade is None else 1 - y_fade
        results.append(dict(
            date=date,
            direction=meta["direction"],
            strategy_entry=meta["entry"],
            prior_label_entry=meta["prior_entry"],
            prior_entry_diff=meta["prior_entry"] - meta["entry"],
            old_y_fade=src["y_fade"],
            old_y_cont=src["y_cont"],
            y_fade_tick=y_fade,
            y_cont_tick=y_cont,
            fade_agrees=(src["y_fade"] == y_fade) if y_fade is not None else None,
            cont_agrees=(src["y_cont"] == y_cont) if y_cont is not None else None,
            status=status,
            breakout_ns=meta["breakout"],
            first_trade_ns=first_ns,
            exit_ns=exit_ns,
            trades_to_exit=used,
        ))
        if i % 25 == 0 or i == len(source):
            fade_bad = sum(row["fade_agrees"] is False for row in results)
            cont_bad = sum(row["cont_agrees"] is False for row in results)
            elapsed = time.time() - started
            eta = elapsed / i * (len(source) - i)
            print(
                f"{i}/{len(source)} elapsed={elapsed:.0f}s eta={eta:.0f}s "
                f"fade_mismatch={fade_bad} cont_mismatch={cont_bad}",
                flush=True,
            )

    with OUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved {OUT_PATH}")


if __name__ == "__main__":
    main()

