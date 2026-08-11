# -*- coding: utf-8 -*-
"""Causal 1-second efficiency / velocity / confluence features per OR breakout.

Data source: ohlcv-1s-full (Databento DBN, full RTH session, 1029 days).
No bid/ask split available -> NO signed aggressor / VPIN here (those need MBO).

Every predictor is strictly CAUSAL: only 1s bars with ts_event < breakout second
are used. The breakout second itself and everything after are excluded so the
feature matrix carries zero look-ahead into the CatBoost model.

Output: one row per labelled breakout (merged on `date`), ready to join with the
existing OR-CB feature tables / labels.
"""

from __future__ import annotations

import glob
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

from progress import track

# ============================================================
# CONFIG
# ============================================================

TICK = 0.25

LABELS = Path(
    r"C:\Users\k_99_\Documents\Indicador ATAS"
    r"\outputs\edge_validation_20260630\tick_labels_486.csv"
)
DBN_ROOT = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup"
    r"\Nautilus_OR\Nautilus_OR\data\raw_dbn_2"
)
OUT_DIR = Path(
    r"C:\Users\k_99_\Documents\Indicador ATAS\outputs\efficiency_1s"
)

# Causal look-back windows (seconds) ending right before the breakout second.
WINDOWS = [5, 10, 30, 60, 120]

# ============================================================
# DBN LOADING (cached per date)
# ============================================================

_DBN_CACHE: dict[str, pd.DataFrame | None] = {}


def load_session(date: str) -> pd.DataFrame | None:
    """Return the full-session 1s OHLCV frame for a date, or None if missing."""
    if date in _DBN_CACHE:
        return _DBN_CACHE[date]
    hits = glob.glob(str(DBN_ROOT / date / "ohlcv-1s-full" / "*.dbn.zst"))
    if not hits:
        _DBN_CACHE[date] = None
        return None
    df = db.DBNStore.from_file(hits[0]).to_df()
    df = df[["open", "high", "low", "close", "volume"]].sort_index()
    # keep memory bounded across 486 dates
    if len(_DBN_CACHE) > 8:
        _DBN_CACHE.clear()
    _DBN_CACHE[date] = df
    return df


def prev_session_hlc(date: str) -> tuple[float, float, float] | None:
    """RTH high/low/close of the most recent prior trading day (causal levels)."""
    all_days = sorted(p.name for p in DBN_ROOT.iterdir() if p.is_dir())
    if date not in all_days:
        return None
    i = all_days.index(date)
    for j in range(i - 1, -1, -1):
        prev = load_session(all_days[j])
        if prev is not None and len(prev):
            return float(prev["high"].max()), float(prev["low"].min()), float(prev["close"].iloc[-1])
    return None

# ============================================================
# FEATURE MATH
# ============================================================

def window_features(win: pd.DataFrame, sign: int, w: int) -> dict[str, float]:
    """Efficiency / velocity / intensity for one causal window.

    sign = +1 for UP breakout, -1 for DOWN (favourable direction).
    """
    if win.empty:
        return {}
    vol = float(win["volume"].sum())
    rng_ticks = (float(win["high"].max()) - float(win["low"].min())) / TICK
    net_ticks = (float(win["close"].iloc[-1]) - float(win["open"].iloc[0])) / TICK
    dir_ticks = net_ticks * sign  # >0 means price already moving toward breakout
    rng_ticks = max(rng_ticks, 1.0)
    volden = max(vol, 1.0)

    ret = np.log(win["close"].to_numpy())
    ret = np.diff(ret) if len(ret) > 1 else np.array([0.0])

    return {
        f"vol_{w}": vol,
        f"rng_ticks_{w}": rng_ticks,
        f"net_ticks_{w}": net_ticks,
        f"dir_ticks_{w}": dir_ticks,
        # efficiency: how much price per contract
        f"vol_per_tick_{w}": vol / rng_ticks,
        f"liq_eff_{w}": abs(net_ticks) / volden * 1000.0,   # ticks per 1000 contracts
        f"amihud_{w}": abs(net_ticks) / volden,             # == Kyle lambda proxy (unsigned)
        # velocity
        f"vel_ticks_s_{w}": rng_ticks / w,
        f"vel_vol_s_{w}": vol / w,
        f"rvol_{w}": float(np.std(ret)),
        # intensity
        f"max1s_vol_{w}": float(win["volume"].max()),
        f"max1s_rng_{w}": (float((win["high"] - win["low"]).max())) / TICK,
    }


def round_dist_ticks(price: float) -> dict[str, float]:
    out = {}
    for step, pts in [("25", 25.0), ("50", 50.0), ("100", 100.0)]:
        nearest = round(price / pts) * pts
        out[f"dist_round_{step}_ticks"] = abs(price - nearest) / TICK
    return out


def build_row(row: pd.Series) -> dict[str, float] | None:
    date = str(row["date"])
    session = load_session(date)
    if session is None or session.empty:
        return None

    breakout = pd.to_datetime(int(row["breakout_ns"]), utc=True)
    sec = breakout.floor("s")
    sign = 1 if str(row["direction"]).upper() == "UP" else -1
    edge = float(row["strategy_entry"])

    # strictly causal: bars before the breakout second
    causal = session.loc[session.index < sec]
    if len(causal) < 5:
        return None

    feats: dict[str, float] = {"date": date}

    for w in WINDOWS:
        win = causal.loc[causal.index >= sec - pd.Timedelta(seconds=w)]
        feats.update(window_features(win, sign, w))

    # acceleration: last 5s velocity vs the 5s before it
    last5 = causal.loc[causal.index >= sec - pd.Timedelta(seconds=5)]
    prev5 = causal.loc[
        (causal.index >= sec - pd.Timedelta(seconds=10))
        & (causal.index < sec - pd.Timedelta(seconds=5))
    ]
    v_last = last5["volume"].sum() / 5.0
    v_prev = prev5["volume"].sum() / 5.0
    feats["accel_vol_s"] = float(v_last - v_prev)
    r_last = (last5["high"].max() - last5["low"].min()) / TICK / 5.0 if len(last5) else 0.0
    r_prev = (prev5["high"].max() - prev5["low"].min()) / TICK / 5.0 if len(prev5) else 0.0
    feats["accel_ticks_s"] = float(r_last - r_prev)

    # session-so-far context (causal): VWAP proxy from 1s closes, range position
    sofar = session.loc[session.index < sec]
    pv = (sofar["close"] * sofar["volume"]).sum()
    vv = sofar["volume"].sum()
    vwap = pv / vv if vv > 0 else edge
    feats["dist_vwap_ticks"] = (edge - vwap) / TICK * sign  # >0 = breakout beyond vwap in dir
    sess_hi = float(sofar["high"].max())
    sess_lo = float(sofar["low"].min())
    span = max(sess_hi - sess_lo, TICK)
    feats["sess_range_pos"] = (edge - sess_lo) / span  # 0..1 location of breakout in day range
    # POC proxy: price bin (1pt) with most 1s volume so far
    binned = (sofar["close"].round(0)).astype(int)
    poc_price = sofar.groupby(binned)["volume"].sum().idxmax()
    feats["dist_poc_ticks"] = (edge - float(poc_price)) / TICK * sign

    # prior-day levels (causal)
    hlc = prev_session_hlc(date)
    if hlc:
        ph, pl, pc = hlc
        feats["dist_pdh_ticks"] = (edge - ph) / TICK
        feats["dist_pdl_ticks"] = (edge - pl) / TICK
        feats["dist_pdc_ticks"] = (edge - pc) / TICK

    feats.update(round_dist_ticks(edge))
    return feats


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lab = pd.read_csv(LABELS)
    print(f"Labels: {len(lab)} rows | {lab['date'].min()} -> {lab['date'].max()}")

    rows = []
    skipped = 0
    for _, row in track(list(lab.iterrows()), label="1s efficiency features"):
        try:
            r = build_row(row)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  ERROR {row['date']}: {exc}")
            r = None
        if r is None:
            skipped += 1
            continue
        rows.append(r)

    out = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    dest = OUT_DIR / "features_efficiency_1s_486.csv"
    out.to_csv(dest, index=False)
    print(f"\nDone. rows={len(out)} skipped={skipped} cols={out.shape[1]}")
    print(f"Wrote: {dest}")
    print("Feature columns:")
    print(", ".join(c for c in out.columns if c != "date"))


if __name__ == "__main__":
    main()
