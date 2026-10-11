"""Opening-range breakout events + honest bracket labels, from 1s bars.

For each session and each OR length we take the first 1s close beyond the OR
high/low after the range closes, enter at the next bar's open, then walk the
1s path to see whether TP or SL came first. A timeout is NOT scored as 0 P&L:
it is marked to market at the exit bar, otherwise the label hands the strategy
a free option and the EV comes out fake.
"""
from __future__ import annotations

import sys
from datetime import time, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA, OR_MINUTES_GRID, OR_OPEN
from progress import track

TICK = 0.25
BARS = DATA / "bars"
OUT = DATA / "events"

ENTRY_CUTOFF = time(11, 0)      # no new breakout entries after this ET time
TIMEOUT_MIN = 60                # flat at market after this many minutes
BRACKETS = [(20, 20), (30, 20), (40, 20), (30, 30), (40, 40), (60, 30), (80, 40)]


def session_frame(day_bars: pd.DataFrame, or_minutes: int) -> dict | None:
    """OR levels and the breakout event for one session / one OR length."""
    t = day_bars.ts_ny.dt.time
    or_end = (pd.Timestamp("2000-01-01") + pd.Timedelta(hours=OR_OPEN.hour,
              minutes=OR_OPEN.minute + or_minutes)).time()
    or_bars = day_bars[(t >= OR_OPEN) & (t < or_end)]
    if or_bars.empty:
        return None

    or_hi, or_lo = or_bars.high.max(), or_bars.low.min()
    after = day_bars[(t >= or_end) & (t < ENTRY_CUTOFF)]
    if after.empty or or_hi <= or_lo:
        return None

    up = after.close > or_hi
    dn = after.close < or_lo
    first = after[up | dn]
    if first.empty:
        return None

    sig = first.iloc[0]
    side = 1 if sig.close > or_hi else -1
    nxt = day_bars[day_bars.ts_utc > sig.ts_utc]
    if nxt.empty:
        return None
    entry_bar = nxt.iloc[0]

    return {"session": day_bars.session.iloc[0], "or_minutes": or_minutes,
            "or_high": or_hi, "or_low": or_lo,
            "or_range_ticks": round((or_hi - or_lo) / TICK),
            "or_volume": int(or_bars.volume.sum()),
            "side": side,
            "signal_ts": sig.ts_utc, "signal_ts_ny": sig.ts_ny,
            "entry_ts": entry_bar.ts_utc, "entry_px": float(entry_bar.open),
            "path": nxt}


def resolve(ev: dict, tp_ticks: int, sl_ticks: int) -> dict:
    """Walk the 1s path and score one bracket. Returns R-multiple and exit kind."""
    side, entry = ev["side"], ev["entry_px"]
    tp = entry + side * tp_ticks * TICK
    sl = entry - side * sl_ticks * TICK
    deadline = ev["entry_ts"] + timedelta(minutes=TIMEOUT_MIN)
    path = ev["path"]
    path = path[path.ts_utc <= deadline]

    for b in path.itertuples(index=False):
        hit_tp = (b.high >= tp) if side > 0 else (b.low <= tp)
        hit_sl = (b.low <= sl) if side > 0 else (b.high >= sl)
        if hit_tp and hit_sl:
            # same 1s bar: assume the adverse side filled first (conservative)
            return {"exit_kind": "ambiguous", "exit_px": sl,
                    "ticks": -sl_ticks, "exit_ts": b.ts_utc}
        if hit_sl:
            return {"exit_kind": "sl", "exit_px": sl,
                    "ticks": -sl_ticks, "exit_ts": b.ts_utc}
        if hit_tp:
            return {"exit_kind": "tp", "exit_px": tp,
                    "ticks": tp_ticks, "exit_ts": b.ts_utc}

    if path.empty:
        return {"exit_kind": "no_path", "exit_px": entry, "ticks": 0,
                "exit_ts": ev["entry_ts"]}
    last = path.iloc[-1]
    ticks = side * (last.close - entry) / TICK
    return {"exit_kind": "timeout", "exit_px": float(last.close),
            "ticks": round(ticks, 2), "exit_ts": last.ts_utc}


def main() -> int:
    files = sorted(BARS.glob("bars_1s_*.parquet"))
    if not files:
        print(f"no bars in {BARS}. run 03_build_bars.py first.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    bars = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    bars = bars.sort_values("ts_utc")
    sessions = list(bars.groupby("session", sort=True))
    print(f"{len(bars):,} bars, {len(sessions)} sessions")

    rows = []
    for _, day_bars in track(sessions, label="OR events + labels"):
        for or_minutes in OR_MINUTES_GRID:
            ev = session_frame(day_bars.reset_index(drop=True), or_minutes)
            if ev is None:
                continue
            base = {k: v for k, v in ev.items() if k != "path"}
            for tp, sl in BRACKETS:
                r = resolve(ev, tp, sl)
                rows.append({**base, "tp_ticks": tp, "sl_ticks": sl,
                             "rr": round(tp / sl, 2),
                             "breakeven_wr": round(sl / (tp + sl), 4),
                             "r_multiple": round(r["ticks"] / sl, 4),
                             **r})

    ev_df = pd.DataFrame(rows)
    ev_df["year"] = pd.to_datetime(ev_df.signal_ts).dt.tz_convert("America/New_York").dt.year
    ev_df.to_parquet(OUT / "or_events.parquet", index=False)
    print(f"\n{len(ev_df):,} labeled event-brackets -> {OUT/'or_events.parquet'}")
    print(ev_df.exit_kind.value_counts().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
