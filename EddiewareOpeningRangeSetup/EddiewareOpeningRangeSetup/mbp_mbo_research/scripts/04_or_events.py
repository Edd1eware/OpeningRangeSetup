"""Opening-range breakout events + honest 1:1 bracket labels, from 1s bars.

SETUP (user spec, treated as ground truth)
------------------------------------------
* Opening range = the single 09:30-09:31 ET M1 candle.
* Entry only from a M1 candle that closes between 09:31 and 09:39 ET.
* The break must be made by the BODY: the M1 close clears the OR level.
  A wick poke is not a signal.
* VWAP (anchored at 09:30) must back the direction: long only above it,
  short only below it.
* Bracket is 1:1, so breakeven WR is exactly 50%, and the target lives inside
  the 30-120 tick band.
* Footprint imbalance is the remaining condition; it needs MBO, so it is added
  in 05_l2_features.py and applied as a filter at evaluation time.

A timeout is NOT scored as 0 P&L: it is marked to market. Scoring it flat hands
the strategy a free option and inflates EV.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (BRACKET_TICKS, DATA, ENTRY_FROM, ENTRY_MODES, ENTRY_TO,
                    LIMIT_VALID_TO, MOVE_MAX_TICKS, MOVE_MIN_TICKS, OR_MINUTES,
                    OR_OPEN, REQUIRE_BODY_BREAK, REQUIRE_VWAP_ALIGN)
from progress import track

TICK = 0.25
BARS = DATA / "bars"
OUT = DATA / "events"
TIMEOUT_MIN = 30          # flat at market 30 min after entry


def to_m1(bars_1s: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1s bars into M1 candles, keyed by the minute's START in ET."""
    g = bars_1s.set_index("ts_ny").resample("1min")
    m1 = pd.DataFrame({"open": g.open.first(), "high": g.high.max(),
                       "low": g.low.min(), "close": g.close.last(),
                       "volume": g.volume.sum()}).dropna(subset=["close"])
    return m1.reset_index().rename(columns={"ts_ny": "minute_ny"})


def add_vwap(bars_1s: pd.DataFrame) -> pd.DataFrame:
    """Session VWAP anchored at 09:30 ET, exactly as the trader's ATAS computes it.

    His VWAP/TWAP indicator is set to Source = Close(NQ), Volume type = Total,
    Session Begin 09:30:00. So the price weighted is the bar's CLOSE, not the
    typical (H+L+C)/3 that most VWAP implementations use. That difference moves
    the line and therefore changes which breaks pass the VWAP condition at all.
    """
    df = bars_1s.copy()
    rth = df.ts_ny.dt.time >= OR_OPEN
    pv = np.where(rth, df.close * df.volume, 0.0)
    vol = np.where(rth, df.volume, 0.0)
    cum_pv, cum_v = np.cumsum(pv), np.cumsum(vol)
    df["vwap"] = np.where(cum_v > 0, cum_pv / np.maximum(cum_v, 1e-9), np.nan)
    return df


def find_signal(bars_1s: pd.DataFrame) -> dict | None:
    """The first qualifying body break inside the entry window, or None."""
    bars_1s = add_vwap(bars_1s)
    m1 = to_m1(bars_1s)
    t = m1.minute_ny.dt.time

    or_mask = (t >= OR_OPEN) & (t < ENTRY_FROM)
    or_bars = m1[or_mask]
    if len(or_bars) < OR_MINUTES:
        return None
    or_hi, or_lo = or_bars.high.max(), or_bars.low.min()
    or_range = round((or_hi - or_lo) / TICK)

    window = m1[(t >= ENTRY_FROM) & (t <= ENTRY_TO)]
    if window.empty or or_range <= 0:
        return None

    # VWAP as of each candidate minute's close = last 1s vwap inside that minute
    vwap_by_min = (bars_1s.set_index("ts_ny").vwap.resample("1min").last()
                   .reindex(window.minute_ny).to_numpy())

    for i, row in enumerate(window.itertuples(index=False)):
        ref = row.close if REQUIRE_BODY_BREAK else row.high
        up = (row.close > or_hi) if REQUIRE_BODY_BREAK else (row.high > or_hi)
        dn = (row.close < or_lo) if REQUIRE_BODY_BREAK else (row.low < or_lo)
        if not (up or dn):
            continue
        side = 1 if up else -1
        vwap = vwap_by_min[i]
        vwap_ok = bool(side > 0 and row.close > vwap) or bool(side < 0 and row.close < vwap)
        if REQUIRE_VWAP_ALIGN and not vwap_ok:
            continue   # the break happened but VWAP did not back it: skip

        # body strength: how much of the candle is body, and how far past the level
        body = abs(row.close - row.open)
        rng = max(row.high - row.low, TICK)
        level = or_hi if side > 0 else or_lo

        minute_end = row.minute_ny + pd.Timedelta(minutes=1)
        nxt = bars_1s[bars_1s.ts_ny >= minute_end]
        if nxt.empty:
            return None
        entry_bar = nxt.iloc[0]
        return {
            "session": bars_1s.session.iloc[0],
            "or_high": float(or_hi), "or_low": float(or_lo),
            "or_range_ticks": int(or_range),
            "or_volume": int(or_bars.volume.sum()),
            "side": side,
            "signal_minute_ny": row.minute_ny,
            "signal_minute_idx": int(row.minute_ny.minute),   # 31..39
            "signal_ts": entry_bar.ts_utc,                    # feature cutoff
            "break_ticks": round((row.close - level) / TICK * side, 2),
            "body_frac": round(body / rng, 3),
            "m1_range_ticks": round(rng / TICK, 1),
            "m1_volume": int(row.volume),
            "vwap": float(vwap) if vwap == vwap else np.nan,
            "vwap_dist_ticks": round((row.close - vwap) / TICK, 1) if vwap == vwap else np.nan,
            "vwap_ok": vwap_ok,
            "entry_ts": entry_bar.ts_utc, "entry_px": float(entry_bar.open),
            "path": nxt,
        }
    return None


def take_entry(ev: dict, mode: str) -> dict | None:
    """Resolve the signal into an actual fill under one entry mode.

    Returns None when that mode would not have taken the trade at all, which is
    itself a result: a mode that skips the bad ones earns its lower frequency.
    """
    path = ev["path"]
    if mode == "market":
        bar = path.iloc[0]
        return {"entry_ts": bar.ts_utc, "entry_px": float(bar.open),
                "filled": True, "fill_wait_s": 0.0, "path_from": 0,
                "no_tp_first_bar": False}

    if mode.startswith("chase_"):
        cap = int(mode.split("_")[1])
        if ev["break_ticks"] > cap:
            return None                      # closed too far past the level
        bar = path.iloc[0]
        return {"entry_ts": bar.ts_utc, "entry_px": float(bar.open),
                "filled": True, "fill_wait_s": 0.0, "path_from": 0,
                "no_tp_first_bar": False}

    if mode == "limit_level":
        level = ev["or_high"] if ev["side"] > 0 else ev["or_low"]
        valid = path[path.ts_ny.dt.time <= LIMIT_VALID_TO]
        if valid.empty:
            return None
        # a buy limit at the OR high fills when trade prints come back down to it
        touched = (valid.low <= level) if ev["side"] > 0 else (valid.high >= level)
        hits = valid[touched]
        if hits.empty:
            return {"filled": False}         # signal taken, never filled
        bar = hits.iloc[0]
        idx = int(path.index.get_loc(hits.index[0]))
        # The fill is known only to have happened SOMEWHERE inside this second.
        # Using the same second's high for the target would book a move that may
        # have occurred before the fill, which is lookahead and it flatters this
        # mode specifically. So on the fill second only the stop may trigger;
        # the target can only be reached from the next second onwards. Same
        # adverse-first convention used for ties everywhere else.
        return {"entry_ts": bar.ts_utc, "entry_px": float(level), "filled": True,
                "fill_wait_s": (bar.ts_utc - path.iloc[0].ts_utc).total_seconds(),
                "path_from": idx, "no_tp_first_bar": True}

    raise ValueError(f"unknown entry mode: {mode}")


def resolve(ev: dict, fill: dict, tp_ticks: int, sl_ticks: int) -> dict:
    """Walk the 1s path from the fill and score one bracket.

    When a single second touches both TP and SL the loss is booked: at 1s
    resolution we cannot know the order, and guessing the favourable one is how
    a flat strategy starts printing a positive EV.
    """
    side, entry, t_in = ev["side"], fill["entry_px"], fill["entry_ts"]
    tp = entry + side * tp_ticks * TICK
    sl = entry - side * sl_ticks * TICK
    path = ev["path"].iloc[fill["path_from"]:]
    path = path[path.ts_utc <= t_in + timedelta(minutes=TIMEOUT_MIN)]
    if path.empty:
        return {"exit_kind": "no_path", "ticks": 0.0, "exit_ts": t_in,
                "mins_to_exit": 0.0}

    no_tp = bool(fill.get("no_tp_first_bar"))
    for i, b in enumerate(path.itertuples(index=False)):
        hit_tp = (b.high >= tp) if side > 0 else (b.low <= tp)
        hit_sl = (b.low <= sl) if side > 0 else (b.high >= sl)
        if i == 0 and no_tp:
            hit_tp = False               # see take_entry: fill timing unknown
        if hit_sl:                      # checked first: conservative on ties
            kind = "ambiguous" if hit_tp else "sl"
            # If the second OPENED beyond the stop the fill is the open, not the
            # stop price: the level was not available any more.
            gap_px = (min(b.open, sl) if side > 0 else max(b.open, sl))
            ticks = side * (gap_px - entry) / TICK
            return {"exit_kind": kind, "ticks": round(float(ticks), 2),
                    "exit_ts": b.ts_utc,
                    "mins_to_exit": (b.ts_utc - t_in).total_seconds() / 60}
        if hit_tp:
            return {"exit_kind": "tp", "ticks": float(tp_ticks), "exit_ts": b.ts_utc,
                    "mins_to_exit": (b.ts_utc - t_in).total_seconds() / 60}

    last = path.iloc[-1]
    return {"exit_kind": "timeout",
            "ticks": round(side * (last.close - entry) / TICK, 2),
            "exit_ts": last.ts_utc,
            "mins_to_exit": (last.ts_utc - t_in).total_seconds() / 60}


def main() -> int:
    files = sorted(BARS.glob("bars_1s_*.parquet"))
    if not files:
        print(f"no bars in {BARS}. run 03_build_bars.py first.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    bars = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)
    bars = bars.sort_values("ts_utc")
    sessions = list(bars.groupby("session", sort=True))
    print(f"{len(bars):,} 1s bars, {len(sessions)} sessions")
    print(f"spec: OR {OR_OPEN}-{ENTRY_FROM}, entries {ENTRY_FROM}-{ENTRY_TO}, "
          f"body break={REQUIRE_BODY_BREAK}, vwap={REQUIRE_VWAP_ALIGN}, "
          f"brackets 1:1 {BRACKET_TICKS} ticks")

    rows, no_signal = [], 0
    for _, day_bars in track(sessions, label="OR events + 1:1 labels"):
        ev = find_signal(day_bars.reset_index(drop=True))
        if ev is None:
            no_signal += 1
            continue
        base = {k: v for k, v in ev.items() if k not in ("path", "entry_ts", "entry_px")}
        for mode in ENTRY_MODES:
            fill = take_entry(ev, mode)
            if fill is None:                       # this mode skipped the setup
                continue
            if not fill["filled"]:                 # limit never came back
                rows.append({**base, "entry_mode": mode, "filled": False,
                             "tp_ticks": np.nan, "sl_ticks": np.nan, "rr": 1.0,
                             "breakeven_wr": 0.5, "ticks": np.nan,
                             "exit_kind": "unfilled", "r_multiple": np.nan,
                             "mins_to_exit": np.nan, "fill_wait_s": np.nan,
                             "entry_px": np.nan})
                continue
            for n in BRACKET_TICKS:
                if not (MOVE_MIN_TICKS <= n <= MOVE_MAX_TICKS):
                    continue
                r = resolve(ev, fill, n, n)
                rows.append({**base, "entry_mode": mode, "filled": True,
                             "entry_px": fill["entry_px"],
                             "entry_ts": fill["entry_ts"],
                             "fill_wait_s": fill["fill_wait_s"],
                             "tp_ticks": n, "sl_ticks": n, "rr": 1.0,
                             "breakeven_wr": 0.5,
                             "r_multiple": round(r["ticks"] / n, 4), **r})

    if not rows:
        print("no qualifying setups found.")
        return 1
    ev_df = pd.DataFrame(rows)
    ev_df["year"] = ev_df.signal_minute_ny.dt.year
    ev_df.to_parquet(OUT / "or_events.parquet", index=False)

    signals = len(sessions) - no_signal
    print(f"\nsessions with a qualifying setup: {signals}/{len(sessions)}"
          f"  ({100*signals/len(sessions):.1f}%)")
    print(f"{len(ev_df):,} rows -> {OUT/'or_events.parquet'}")

    print("\n--- entry mode comparison (all brackets pooled) ---")
    out = []
    for mode, g in ev_df.groupby("entry_mode"):
        taken = g.session.nunique()
        f = g[g.filled]
        out.append({
            "entry_mode": mode,
            "sesiones tomadas": taken,
            "% de signals": round(100 * taken / max(signals, 1), 1),
            "fill %": round(100 * f.session.nunique() / max(taken, 1), 1),
            "WR %": round(100 * (f.ticks > 0).mean(), 1) if len(f) else np.nan,
            "EV ticks": round(f.ticks.mean(), 2) if len(f) else np.nan,
            "espera fill (s)": round(f.fill_wait_s.mean(), 1) if len(f) else np.nan,
        })
    print(pd.DataFrame(out).to_string(index=False))

    print("\n--- market entry: exit mix by bracket size ---")
    mk = ev_df[(ev_df.entry_mode == "market") & ev_df.filled]
    mix = mk.pivot_table(index="tp_ticks", columns="exit_kind",
                         values="session", aggfunc="count", fill_value=0)
    mix["WR %"] = (100 * mix.get("tp", 0) / mix.sum(axis=1)).round(1)
    print(mix.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
