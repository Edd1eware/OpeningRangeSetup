"""Build a tick-exact aggressor tape from the 150 `trades` DBN files.

Why this exists
---------------
The small-stop research question cannot be answered from 1s OHLC bars: a single
second in the first minutes of NQ has a median range of 15 ticks and a p90 of
30, so an 8-25 tick bracket is usually resolved INSIDE one second and the
TP-vs-SL ordering is simply not recoverable from open/high/low/close. The
`trades` schema is tick-exact and already paid for, for all 150 EDT 2026
sessions, 09:25-10:30 ET.

Output: one parquet with every trade, normalised to compact integer columns.

    session   date32    the ET session date
    ts_ns     int64     ts_event in UTC nanoseconds (monotone within a session)
    px_t      int32     price in TICKS: round(price / 0.25). Integer, so no
                        float comparison ever decides whether a stop was hit.
    size      int32     trade size, cast off uint (see gotcha below)
    sign      int8      +1 buy aggressor, -1 sell aggressor, 0 = side not
                        reported ('N'). See the note below: these rows STAY.

Aggressor convention (this cost the project a whole analysis once)
------------------------------------------------------------------
Verified against the installed databento_dbn/_lib.pyi `Side` docstring:
    ASK = "a sell order or sell aggressor in a trade"
    BID = "a buy order or a buy aggressor in a trade"
So for TradeMsg: side == 'A' is the SELL aggressor (it hits the bid and adds to
traded BID volume) and side == 'B' is the BUY aggressor (it lifts the ask).
An earlier version of 05_l2_features.py had this inverted, which flipped the
sign of CVD, delta and every diagonal imbalance count. Do not "simplify" it.

Gotchas
-------
* `size` arrives as an unsigned integer. Any subtraction done before casting
  wraps around to ~1.8e19 instead of going negative. Cast first, always.
* `DBNStore` memory-maps the file it reads, so on Windows the handle must be
  dropped before the file can be touched again. We only read here, but the
  store is deleted per iteration anyway to keep memory flat.
* Rows with side == 'N' (no aggressor reported) are KEPT, with sign = 0.
  An earlier version of this script dropped them outright, which Codex flagged:
  they are legitimate prints, so removing them punches holes in the PRICE PATH
  and a barrier crossing or a timeout reference can silently vanish. The right
  split is: exclude sign == 0 from SIGNED-VOLUME features, keep it in the path.
  The count is reported so the decision stays visible instead of implied.
"""
from __future__ import annotations

import gc
import sys
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATA, NY  # noqa: E402
from progress import track  # noqa: E402

TICK = 0.25
OUT = DATA / "tape" / "tape_trades_2026.parquet"
TRADES_DIR = DATA / "trades"


def load_one(path: Path) -> tuple[pd.DataFrame | None, int, int]:
    """Read one trades DBN into the compact integer schema.

    Returns (frame, raw_rows, n_side_unknown). The frame keeps every print,
    including side == 'N', which gets sign = 0.
    """
    store = db.DBNStore.from_file(path)
    try:
        d = store.to_df(price_type="float", tz="UTC").reset_index()
    finally:
        del store
        gc.collect()

    raw_rows = len(d)
    if d.empty:
        return None, raw_rows, 0

    side = d["side"].to_numpy()
    n_unknown = int((~np.isin(side, ("A", "B"))).sum())

    ts = pd.to_datetime(d["ts_event"], utc=True)
    session = ts.dt.tz_convert(NY).dt.date

    # +1 buy aggressor ('B'), -1 sell aggressor ('A'), 0 anything else ('N')
    sign = np.where(side == "B", 1, np.where(side == "A", -1, 0)).astype("int8")

    out = pd.DataFrame({
        "session": pd.to_datetime(session).astype("datetime64[s]"),
        "ts_ns": ts.astype("int64").to_numpy(),
        # round, not floor: float prices land on x.9999999 often enough to matter
        "px_t": np.rint(d["price"].to_numpy() / TICK).astype("int32"),
        # cast BEFORE anything arithmetic touches it (uint wrap-around bug)
        "size": d["size"].to_numpy().astype("int64").astype("int32"),
        "sign": sign,
        # Codex: stable timestamp sorting alone does not prove causal order
        # across tied timestamps. Keep the venue sequence so the original
        # record order stays recoverable.
        "sequence": d["sequence"].to_numpy().astype("int64"),
    })
    # sort by (ts, sequence) so ties keep the exchange's own ordering
    out = out.sort_values(["ts_ns", "sequence"], kind="stable")
    return out.reset_index(drop=True), raw_rows, n_unknown


def main() -> None:
    files = sorted(TRADES_DIR.glob("NQ_trades_*.dbn.zst"))
    if not files:
        raise SystemExit(f"no trades files in {TRADES_DIR}")

    print(f"tape builder: {len(files)} sessions from {TRADES_DIR}", flush=True)

    frames: list[pd.DataFrame] = []
    skipped: list[str] = []
    dropped_no_side = 0
    raw_rows = 0

    for path in track(files, label="tape build"):
        try:
            part, n_raw, n_unknown = load_one(path)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            skipped.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        raw_rows += n_raw
        dropped_no_side += n_unknown
        if part is None or part.empty:
            skipped.append(f"{path.name}: no rows")
            continue
        frames.append(part)

    if not frames:
        raise SystemExit("every file failed; nothing to write")

    tape = pd.concat(frames, ignore_index=True)
    tape = (tape.sort_values(["session", "ts_ns", "sequence"], kind="stable")
            .reset_index(drop=True))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tape.to_parquet(OUT, index=False, compression="zstd")

    # --- report -------------------------------------------------------------
    ny = pd.to_datetime(tape["ts_ns"], utc=True).dt.tz_convert(NY)
    per_session = tape.groupby("session").size()

    print("", flush=True)
    print(f"wrote {OUT}", flush=True)
    print(f"  rows            {len(tape):,}", flush=True)
    print(f"  sessions        {tape['session'].nunique()}", flush=True)
    print(f"  file size       {OUT.stat().st_size / 1e6:.1f} MB", flush=True)
    print(f"  trades/session  min {per_session.min():,}  "
          f"median {int(per_session.median()):,}  max {per_session.max():,}",
          flush=True)
    print(f"  ET clock span   {ny.dt.time.min()} -> {ny.dt.time.max()}", flush=True)
    print(f"  buy aggressor   {(tape['sign'] == 1).mean():.3%} of trades", flush=True)
    print(f"  sell aggressor  {(tape['sign'] == -1).mean():.3%} of trades", flush=True)
    print(f"  side UNKNOWN    {(tape['sign'] == 0).sum():,} rows "
          f"({(tape['sign'] == 0).mean():.4%}) -- kept in the price path, "
          f"excluded from signed volume", flush=True)
    print(f"  size            min {tape['size'].min()} "
          f"median {int(tape['size'].median())} max {tape['size'].max():,}",
          flush=True)
    print(f"  px_t range      {tape['px_t'].min():,} -> {tape['px_t'].max():,}",
          flush=True)
    print(f"  raw DBN rows    {raw_rows:,} -> kept {len(tape):,} "
          f"(lost {raw_rows - len(tape):,})", flush=True)
    if skipped:
        print(f"  SKIPPED {len(skipped)}:", flush=True)
        for s in skipped:
            print(f"    {s}", flush=True)


if __name__ == "__main__":
    main()
