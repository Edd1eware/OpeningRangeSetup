"""Premarket and overnight context for every OR signal, from the 1s bars.

All of it is known BEFORE 09:31, so none of it can leak: the latest timestamp
any feature touches is 09:31:00 ET, and the entry is at or after that.

Windows, all ET:
  overnight  18:00 previous session -> 09:30   (the Globex session)
  premarket  04:00 -> 09:30                    (European + early US hours)
  last hour  08:30 -> 09:30                     (where the open is actually set)

The point is not to add columns. It is to find out whether the day's character
is visible before the bell, because the path statistics show the breakout itself
carries no edge after costs.
"""
from __future__ import annotations

import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA
from progress import track

TICK = 0.25
EVENTS = DATA / "events" / "or_events.parquet"
BARS = DATA / "bars"
OUT = DATA / "features"

PM_START = time(4, 0)
LAST_HOUR = time(8, 30)
OPEN_T = time(9, 30)
OR_END = time(9, 31)
ON_START = time(18, 0)


def volume_profile(df: pd.DataFrame, va_pct: float = 0.70) -> dict:
    """Price-level volume profile of a window: POC and the value area.

    Each 1s bar spreads its volume uniformly over the tick levels it covered.
    That is an approximation - the true distribution needs trade prints - but it
    is unbiased with respect to direction, which is what matters here: a profile
    built from closes alone would lean towards wherever the second ended.
    """
    if df.empty:
        return {}
    lo_lvl = np.round(df.low.to_numpy() / TICK).astype(np.int64)
    hi_lvl = np.round(df.high.to_numpy() / TICK).astype(np.int64)
    vol = df.volume.to_numpy(float)
    span = (hi_lvl - lo_lvl + 1).astype(float)

    lo, hi = int(lo_lvl.min()), int(hi_lvl.max())
    hist = np.zeros(hi - lo + 2, float)
    per = vol / span                      # volume per tick level of each bar
    # accumulate with a difference array: O(bars), not O(bars x levels)
    np.add.at(hist, lo_lvl - lo, per)
    np.add.at(hist, hi_lvl - lo + 1, -per)
    prof = np.cumsum(hist)[:hi - lo + 1]

    total = prof.sum()
    if total <= 0:
        return {}
    poc_i = int(np.argmax(prof))
    # grow a window out from the POC until it holds va_pct of the volume
    lo_i = hi_i = poc_i
    acc = prof[poc_i]
    while acc < va_pct * total and (lo_i > 0 or hi_i < len(prof) - 1):
        left = prof[lo_i - 1] if lo_i > 0 else -1.0
        right = prof[hi_i + 1] if hi_i < len(prof) - 1 else -1.0
        if right >= left:
            hi_i += 1
            acc += prof[hi_i]
        else:
            lo_i -= 1
            acc += prof[lo_i]
    return {"poc": (lo + poc_i) * TICK,
            "val": (lo + lo_i) * TICK,
            "vah": (lo + hi_i) * TICK,
            "va_width_ticks": float(hi_i - lo_i),
            "poc_share": float(prof[poc_i] / total)}


def window_stats(df: pd.DataFrame, prefix: str) -> dict:
    """Range, volume and close position for one time window."""
    if df.empty:
        return {}
    hi, lo = float(df.high.max()), float(df.low.min())
    rng = (hi - lo) / TICK
    close = float(df.close.iloc[-1])
    vol = float(df.volume.sum())
    out = {f"{prefix}_range_ticks": round(rng, 1),
           f"{prefix}_volume": vol,
           f"{prefix}_bars": len(df)}
    # where the window ended inside its own range: 1.0 = at the high
    out[f"{prefix}_close_pos"] = round((close - lo) / max(hi - lo, TICK), 3)
    tp = (df.high + df.low + df.close) / 3
    vw = float((tp * df.volume).sum() / max(vol, 1e-9))
    out[f"{prefix}_vwap_dist_ticks"] = round((close - vw) / TICK, 1)
    # net drift of the window, in ticks
    out[f"{prefix}_drift_ticks"] = round((close - float(df.close.iloc[0])) / TICK, 1)
    return out


def main() -> int:
    if not EVENTS.exists():
        print(f"no events at {EVENTS}. run 04_or_events.py first.")
        return 1
    ev = pd.read_parquet(EVENTS)
    sigs = ev.drop_duplicates("session")[["session", "side", "or_high", "or_low"]]

    bars = pd.concat((pd.read_parquet(f) for f in sorted(BARS.glob("bars_1s_*.parquet"))),
                     ignore_index=True).sort_values("ts_utc")
    bars["t"] = bars.ts_ny.dt.time
    sessions = sorted(bars.session.unique())
    prev_of = {s: sessions[i - 1] for i, s in enumerate(sessions) if i}
    by_session = {s: g.reset_index(drop=True) for s, g in bars.groupby("session")}
    print(f"{len(sigs)} signals, {len(sessions)} sessions of 1s bars")

    rows = []
    for r in track(list(sigs.itertuples(index=False)), label="premarket features"):
        day = by_session.get(r.session)
        if day is None:
            continue
        feat = {"session": r.session}

        pre = day[(day.t >= PM_START) & (day.t < OPEN_T)]
        feat.update(window_stats(pre, "pm"))
        feat.update(window_stats(day[(day.t >= LAST_HOUR) & (day.t < OPEN_T)], "h1"))

        # Premarket volume profile and where the broken level sits in it.
        # The hypothesis worth falsifying: a break that starts from INSIDE the
        # premarket value area is fading back into accepted price, while a break
        # that is already beyond VAH/VAL has nothing left to reject it.
        vp = volume_profile(pre)
        if vp:
            level = r.or_high if r.side > 0 else r.or_low
            feat["pm_poc"] = vp["poc"]
            feat["pm_va_width_ticks"] = vp["va_width_ticks"]
            feat["pm_poc_share"] = round(vp["poc_share"], 4)
            feat["lvl_to_poc_ticks"] = round((level - vp["poc"]) / TICK * r.side, 1)
            feat["lvl_to_vah_ticks"] = round((level - vp["vah"]) / TICK, 1)
            feat["lvl_to_val_ticks"] = round((level - vp["val"]) / TICK, 1)
            feat["lvl_inside_va"] = int(vp["val"] <= level <= vp["vah"])
            # for a long the level must clear VAH, for a short it must clear VAL
            feat["lvl_beyond_va"] = int(level > vp["vah"] if r.side > 0
                                        else level < vp["val"])
            if feat.get("pm_range_ticks"):
                feat["va_over_pm_range"] = round(
                    vp["va_width_ticks"] / feat["pm_range_ticks"], 3)

        # the Globex session: 18:00 of the previous calendar session to 09:30
        prev = by_session.get(prev_of.get(r.session))
        on_parts = [day[day.t < OPEN_T]]
        if prev is not None:
            on_parts.insert(0, prev[prev.t >= ON_START])
        on = pd.concat(on_parts, ignore_index=True)
        # The volume roll of the continuous symbol fires at 20:00 ET and moves
        # price by the calendar spread (+872 to +1271 ticks measured in 2026).
        # Keeping both contracts in one window would invent a huge overnight
        # range, so only the leg that matches the session's contract is kept.
        if "instrument_id" in on.columns:
            on = on[on.instrument_id == day.instrument_id.iloc[-1]]
        feat.update(window_stats(on, "on"))

        # the gap: previous RTH close (16:00) to the 09:30 open.
        # Skipped across a contract roll: there the continuous series jumps by
        # the calendar spread (measured at +437 points in Sep 2026), which would
        # enter the model as a fake 1700-tick gap.
        rolled = (prev is not None and "instrument_id" in day.columns
                  and day.instrument_id.iloc[0] != prev.instrument_id.iloc[-1])
        feat["rolled"] = int(bool(rolled))
        if prev is not None and not rolled:
            prev_rth = prev[(prev.t >= OPEN_T) & (prev.t <= time(16, 0))]
            if not prev_rth.empty and not pre.empty:
                prev_close = float(prev_rth.close.iloc[-1])
                open_px = float(day[day.t >= OPEN_T].open.iloc[0]) if (day.t >= OPEN_T).any() else np.nan
                feat["gap_ticks"] = round((open_px - prev_close) / TICK, 1)
                feat["gap_aligned"] = feat["gap_ticks"] * r.side
                feat["prev_rth_range_ticks"] = round(
                    (prev_rth.high.max() - prev_rth.low.min()) / TICK, 1)

        # how the OR candle compares with the premarket it came out of
        or_bar = day[(day.t >= OPEN_T) & (day.t < OR_END)]
        if not or_bar.empty:
            or_rng = (or_bar.high.max() - or_bar.low.min()) / TICK
            feat["or_range_ticks_chk"] = round(or_rng, 1)
            if feat.get("pm_range_ticks"):
                feat["or_over_pm_range"] = round(or_rng / feat["pm_range_ticks"], 3)
            if feat.get("h1_range_ticks"):
                feat["or_over_h1_range"] = round(or_rng / max(feat["h1_range_ticks"], 1), 3)
            # did the OR break out of the premarket range at all?
            if not pre.empty:
                feat["or_above_pm_high"] = int(or_bar.high.max() > pre.high.max())
                feat["or_below_pm_low"] = int(or_bar.low.min() < pre.low.min())
            feat["or_volume_chk"] = float(or_bar.volume.sum())
            if feat.get("h1_volume"):
                # volume surge: OR minute vs the average minute of the last hour
                feat["or_vol_surge"] = round(
                    or_bar.volume.sum() / max(feat["h1_volume"] / 60.0, 1e-9), 2)
        rows.append(feat)

    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "premarket_features.parquet", index=False)
    print(f"\n{len(df)} rows x {df.shape[1]} cols -> "
          f"{OUT/'premarket_features.parquet'}")

    pd.set_option("display.width", 220)
    show = [c for c in ("pm_range_ticks", "h1_range_ticks", "on_range_ticks",
                        "gap_ticks", "or_range_ticks_chk", "or_over_h1_range",
                        "or_vol_surge", "pm_close_pos") if c in df.columns]
    print("\nresumen (ticks salvo donde se indique):")
    print(df[show].describe().round(2).to_string())
    if "or_above_pm_high" in df.columns:
        print(f"\nla vela OR rompio el alto del premarket: "
              f"{100*df.or_above_pm_high.mean():.1f}% de las sesiones")
        print(f"la vela OR rompio el bajo del premarket: "
              f"{100*df.or_below_pm_low.mean():.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
