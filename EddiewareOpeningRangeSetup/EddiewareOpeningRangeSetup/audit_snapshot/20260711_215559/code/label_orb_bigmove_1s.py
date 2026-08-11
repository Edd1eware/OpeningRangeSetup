# -*- coding: utf-8 -*-
"""ORB first-touch bracket backtest on 1s bars (lookahead label = target).

OR = first RTH minute (13:30:00-13:30:59 UTC = 09:30 ET) high/low.
Breakout = first 1s bar from 13:31:00 piercing OR high (UP) or OR low (DOWN),
first side wins. Entry at the pierced OR level.

For each TP/SL bracket we walk forward bar by bar and record which is touched
FIRST (path dependent). Conservative tie rule: if a single 1s bar spans both
TP and SL, count it as a LOSS. Timeout = neither touched by session end.

Reports the year x metric table per the project backtest standard.
"""

from __future__ import annotations

import glob
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from progress import track

TICK = 0.25
OR_START = "13:30:00"
OR_END = "13:31:00"      # exclusive -> first 60s
SCAN_START = "13:31:00"

# brackets to test: (tp_ticks, sl_ticks). RR = tp/sl.
BRACKETS = [(60, 60), (60, 40), (60, 30), (60, 20)]
COMMISSION_TICKS = 2.0  # round-trip assumption for EV neto

DBN_ROOT = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
    r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_2"
)
OUT_DIR = Path(r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\orb_bigmove_1s")


def load_session(date: str) -> pd.DataFrame | None:
    hits = glob.glob(str(DBN_ROOT / date / "ohlcv-1s-full" / "*.dbn.zst"))
    if not hits:
        return None
    df = db.DBNStore.from_file(hits[0]).to_df()
    return df[["open", "high", "low", "close", "volume"]].sort_index()


def find_breakout(df: pd.DataFrame):
    day = df.index[0].strftime("%Y-%m-%d")
    or_win = df.between_time(OR_START, OR_END, inclusive="left")
    if or_win.empty:
        return None
    or_high = float(or_win["high"].max())
    or_low = float(or_win["low"].min())
    post = df.loc[df.index >= pd.Timestamp(f"{day} {SCAN_START}", tz="UTC")]
    if post.empty:
        return None
    up = post.index[post["high"] > or_high]
    dn = post.index[post["low"] < or_low]
    t_up = up[0] if len(up) else None
    t_dn = dn[0] if len(dn) else None
    if t_up is None and t_dn is None:
        return None
    if t_dn is None or (t_up is not None and t_up <= t_dn):
        return "UP", t_up, or_high, 1, post, or_high, or_low
    return "DOWN", t_dn, or_low, -1, post, or_high, or_low


def bracket_outcome(fwd: pd.DataFrame, entry: float, sign: int, tp_t: int, sl_t: int) -> int:
    """+1 win, -1 loss, 0 timeout. Conservative: same-bar both-touch = loss."""
    if sign == 1:
        tp, sl = entry + tp_t * TICK, entry - sl_t * TICK
        for h, l in zip(fwd["high"].to_numpy(), fwd["low"].to_numpy()):
            hit_sl = l <= sl
            hit_tp = h >= tp
            if hit_sl:
                return -1
            if hit_tp:
                return 1
    else:
        tp, sl = entry - tp_t * TICK, entry + sl_t * TICK
        for h, l in zip(fwd["high"].to_numpy(), fwd["low"].to_numpy()):
            hit_sl = h >= sl
            hit_tp = l <= tp
            if hit_sl:
                return -1
            if hit_tp:
                return 1
    return 0


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dates = sorted(p.name for p in DBN_ROOT.iterdir() if p.is_dir())
    print(f"Dates: {len(dates)} | {dates[0]} -> {dates[-1]}")

    rows = []
    load_fail = 0
    for d in track(dates, label="ORB bracket"):
        try:
            df = load_session(d)
            if df is None or df.empty:
                load_fail += 1
                continue
            bo = find_breakout(df)
            if bo is None:
                continue
            direction, bt, entry, sign, post, or_high, or_low = bo
            fwd = post.loc[post.index >= bt]
            rec = {
                "date": d, "direction": direction,
                "or_range_ticks": (or_high - or_low) / TICK,
                "breakout_utc": bt.strftime("%H:%M:%S"), "entry": entry,
            }
            for tp_t, sl_t in BRACKETS:
                rec[f"out_{tp_t}_{sl_t}"] = bracket_outcome(fwd, entry, sign, tp_t, sl_t)
            rows.append(rec)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {d}: {exc}")

    out = pd.DataFrame(rows)
    out["year"] = pd.to_datetime(out["date"]).dt.year
    dest = OUT_DIR / "orb_bracket_labels_1s.csv"
    out.to_csv(dest, index=False)
    print(f"\nBreakouts: {len(out)} | load_fail: {load_fail}")
    print(f"Wrote: {dest}")

    months = out["date"].str.slice(0, 7).nunique()
    for tp_t, sl_t in BRACKETS:
        col = f"out_{tp_t}_{sl_t}"
        rr = tp_t / sl_t
        be = sl_t / (tp_t + sl_t) * 100  # breakeven WR %
        print(f"\n=== TP {tp_t} / SL {sl_t}  (R:R {rr:.2f}, breakeven WR {be:.1f}%) ===")
        print(f"{'year':>6} {'n':>5} {'t/mo':>5} {'WR%':>6} {'PF':>6} "
              f"{'EVbr':>7} {'EVnet':>7} {'timeout':>8}")
        for y, g in out.groupby("year"):
            _row(g, col, tp_t, sl_t, str(y))
        _row(out, col, tp_t, sl_t, "TOTAL", months)


def _row(g, col, tp_t, sl_t, label, months=None):
    v = g[col]
    wins = int((v == 1).sum())
    losses = int((v == -1).sum())
    tmo = int((v == 0).sum())
    dec = wins + losses
    wr = wins / dec * 100 if dec else 0.0
    pf = (wins * tp_t) / (losses * sl_t) if losses else float("inf")
    ev_br = (wins * tp_t - losses * sl_t) / dec if dec else 0.0
    ev_net = ev_br - COMMISSION_TICKS
    if months is None:
        yr = pd.to_datetime(g["date"]).dt.to_period("M").nunique()
    else:
        yr = months
    tmo_mo = len(g) / max(yr, 1)
    print(f"{label:>6} {len(g):>5} {tmo_mo:>5.1f} {wr:>5.1f}% {pf:>6.2f} "
          f"{ev_br:>7.1f} {ev_net:>7.1f} {tmo:>8}")


if __name__ == "__main__":
    main()
