"""Relabel the 127-session fade universe from ordered MBO trade events.

This removes the remaining within-second ambiguity from the scratchpad labels.
The strategy is a fade of a DOWN breakout: buy at OR low, TP/SL 30 ticks,
with an evaluation cutoff at 09:50 ET (19 minutes after the OR lock).
"""

from __future__ import annotations

import csv
import glob
import pickle
import time
from pathlib import Path

import databento as db
import duckdb


ROOT = Path(r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\Nautilus_OR\Nautilus_OR")
SOURCE_DB_PATH = ROOT / "data" / "orb_features.duckdb"
RAW_ROOT = ROOT / "data" / "raw_dbn"
SCRATCH = Path(
    r"C:\Users\k_99_\AppData\Local\Temp\claude"
    r"\C--Users-k-99--Desktop\59a5d941-0bcb-4a83-9f25-1c27f99384b9\scratchpad"
)
WIDE_PATH = SCRATCH / "fade_wide_matrix.pkl"
OUT_DIR = Path(__file__).resolve().parent / "outputs" / "edge_validation_20260630"
OUT_PATH = OUT_DIR / "tick_labels_127.csv"
DB_PATH = OUT_DIR / "orb_features_snapshot.duckdb"

TICK = 0.25
TP_TICKS = 30
SL_TICKS = 30


def exact_label(mbo_path: str, breakout_ns: int, cutoff_ns: int, entry: float):
    """Return outcome from ordered trades at/after breakout, plus diagnostics.

    Chunked ndarray decoding is dramatically faster and lighter than materializing
    the complete MBO file as a pandas DataFrame.
    """
    tp = entry + TP_TICKS * TICK
    sl = entry - SL_TICKS * TICK
    used = 0
    first_ns = None

    store = db.DBNStore.from_file(mbo_path)
    for chunk in store.to_ndarray(count=500_000):
        # breakout_ts in DuckDB was built from the MBO DataFrame index, which
        # is ts_recv for this schema. Keep all comparisons in that clock.
        recv_ns = chunk["ts_recv"]
        if len(recv_ns) == 0 or recv_ns[-1] < breakout_ns:
            continue
        if recv_ns[0] > cutoff_ns:
            break
        trade_mask = (
            (chunk["action"] == b"T")
            & (recv_ns >= breakout_ns)
            & (recv_ns <= cutoff_ns)
        )
        trade_rows = chunk[trade_mask]
        if len(trade_rows) == 0:
            continue
        if first_ns is None:
            first_ns = int(trade_rows["ts_recv"][0])
        prices = trade_rows["price"].astype("float64") / 1_000_000_000
        hit = (prices >= tp) | (prices <= sl)
        hit_idx = hit.nonzero()[0]
        if len(hit_idx):
            idx = int(hit_idx[0])
            used += idx + 1
            outcome = 1 if prices[idx] >= tp else 0
            return outcome, int(trade_rows["ts_recv"][idx]), used, first_ns
        used += len(trade_rows)
    return None, None, used, first_ns


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with WIDE_PATH.open("rb") as handle:
        wide = pickle.load(handle)
    by_date = {str(row["date"]): row for row in wide}

    con = duckdb.connect(str(DB_PATH), read_only=True)
    rows = con.execute(
        """
        SELECT CAST(b.session_date AS VARCHAR), b.breakout_ts, b.direction,
               l.entry_price, ol.locked_ts, ol.or_low * 0.25 AS or_low
        FROM breakout_features b
        JOIN labels l USING (session_date)
        JOIN or_levels ol USING (session_date)
        ORDER BY b.session_date
        """
    ).fetchall()
    con.close()
    metadata = {
        date: dict(
            breakout_ns=int(breakout_ns),
            direction=direction,
            label_entry=float(entry),
            entry=float(or_low),
            locked_ns=int(locked_ns),
            or_low=float(or_low),
        )
        for date, breakout_ns, direction, entry, locked_ns, or_low in rows
        if date in by_date
    }

    results = []
    started = time.time()
    for i, date in enumerate(sorted(by_date), start=1):
        src = by_date[date]
        meta = metadata[date]
        if meta["direction"] != "DOWN":
            raise ValueError(f"Unexpected direction for {date}: {meta['direction']}")

        matches = glob.glob(str(RAW_ROOT / date / "mbo" / "*.zst"))
        if not matches:
            outcome = exit_ns = first_ns = None
            used = 0
            status = "NO_MBO"
        else:
            cutoff_ns = meta["locked_ns"] + 19 * 60 * 1_000_000_000
            outcome, exit_ns, used, first_ns = exact_label(
                matches[0], meta["breakout_ns"], cutoff_ns, meta["entry"]
            )
            status = "OK" if outcome is not None else "NO_TOUCH"

        results.append(
            dict(
                date=date,
                y_1s=src["y"],
                y_tick=outcome,
                agrees=(outcome == src["y"]) if outcome is not None else None,
                status=status,
                strategy_entry=meta["entry"],
                prior_label_entry=meta["label_entry"],
                prior_entry_diff=meta["label_entry"] - meta["entry"],
                breakout_ns=meta["breakout_ns"],
                first_trade_ns=first_ns,
                exit_ns=exit_ns,
                trades_to_exit=used,
            )
        )
        if i % 5 == 0 or i == len(by_date):
            mismatches = sum(r["agrees"] is False for r in results)
            elapsed = time.time() - started
            eta = elapsed / i * (len(by_date) - i)
            print(
                f"{i}/{len(by_date)} elapsed={elapsed:.0f}s eta={eta:.0f}s "
                f"mismatches={mismatches}",
                flush=True,
            )

    with OUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved {OUT_PATH}")


if __name__ == "__main__":
    main()
