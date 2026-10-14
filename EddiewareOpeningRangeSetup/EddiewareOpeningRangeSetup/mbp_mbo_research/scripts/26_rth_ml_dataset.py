"""Build the full-RTH decision dataset: wide causal features + barrier labels.

Pre-registered. This is the gate that decides where the remaining Databento
budget goes. Every hand-built rule the project tested (ORB follow/fade, tape
aggressor imbalance, absorption, drive) came back flat or negative. Those are
~20 points sampled by hand out of a large hypothesis space. A gradient-boosted
model over a wide causal feature set samples that space far more densely, so a
clean negative here is much stronger evidence than 20 more hand rules, and a
positive gives a direction worth paying for.

What is fixed before the first run
----------------------------------
* Universe      : 150 EDT sessions, 2026-03-09 .. 2026-10-09, 1s bars.
* Decision grid : every 60s from 09:35 to 15:30 ET. 09:30-09:35 is excluded so
                  every feature window has session data behind it.
* Entry         : open of the next second after the decision. Always fills.
* Barriers      : symmetric K ticks, K in {20, 40}. Timeout 1800s, marked TO
                  MARKET, never to zero (marking a timeout flat hands the
                  strategy a free option).
* Ties          : if one 1s bar touches both barriers, the STOP is charged. At
                  1s resolution the order is unknowable and assuming the
                  favourable one is how fake EV gets manufactured.
* Target        : realised R of a trade opened at that decision. Long and short
                  are computed SEPARATELY, not assumed to be mirror images:
                  the tie rule and the timeout make them asymmetric.

Cost, model, walk-forward and the placebo live in 27_rth_ml_eval.py so the
dataset can be rebuilt without re-running the search, and so the search cannot
quietly reach back and change how a label was made.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
from progress import track

TICK = 0.25
TIMEOUT_S = 1800
BRACKETS = (20, 40)
GRID_S = 60
OPEN_SEC = 9 * 3600 + 30 * 60
DEC_FROM_SEC = (9 * 3600 + 35 * 60) - OPEN_SEC
DEC_TO_SEC = (15 * 3600 + 30 * 60) - OPEN_SEC


def load_bars() -> pd.DataFrame:
    """Every 1s bar with a real ET clock string.

    DuckDB renders TIMESTAMP WITH TIME ZONE in its session timezone, which
    defaults to the machine's local zone. On this machine that is UTC-6, so the
    09:30 ET open prints as 07:30 unless TimeZone is set explicitly. The stored
    value was always correct; only the rendering was not.
    """
    import duckdb
    con = duckdb.connect()
    con.execute("SET TimeZone='America/New_York'")
    # every year on disk, not just 2026: the 2021-2025 download exists to make
    # the daily-frequency tests decidable, and a hardcoded 2026 filename would
    # silently keep every downstream script at the old 150-session sample
    src = (C.DATA / "bars").as_posix() + "/bars_1s_*.parquet"
    df = con.sql(f"""
        select session,
               epoch(ts_ny)::BIGINT       as ep,
               strftime(ts_ny,'%H:%M:%S') as et,
               open, high, low, close, volume
        from read_parquet('{src}')
        order by session, ts_ny
    """).df()
    con.close()
    return df


def session_grid(g: pd.DataFrame) -> dict:
    """Reindex one session's RTH onto a dense 1-second grid.

    A second with no trade is not a missing observation: price did not move and
    no new extreme was set. Close is forward filled and high/low collapse onto
    it, which is what the barrier scan needs so that the timeout counts elapsed
    SECONDS rather than elapsed prints.
    """
    et = g["et"].to_numpy()
    rth = (et >= "09:30:00") & (et <= "16:00:00")
    r = g.loc[rth]
    if len(r) < 3000:
        return {}
    ep0 = int(r.ep.iloc[0])
    n = int(r.ep.iloc[-1]) - ep0 + 1
    idx = r.ep.to_numpy() - ep0

    close = np.full(n, np.nan)
    close[idx] = r.close.to_numpy()
    close = pd.Series(close).ffill().bfill().to_numpy()

    op = close.copy(); op[idx] = r.open.to_numpy()
    hi = close.copy(); hi[idx] = r.high.to_numpy()
    lo = close.copy(); lo[idx] = r.low.to_numpy()
    vol = np.zeros(n); vol[idx] = r.volume.to_numpy().astype(float)

    pre = g.loc[et < "09:30:00"]
    on_hi = float(pre.high.max()) if len(pre) else float(hi[:60].max())
    on_lo = float(pre.low.min()) if len(pre) else float(lo[:60].min())
    return dict(n=n, open=op, high=hi, low=lo, close=close, vol=vol,
                on_hi=on_hi, on_lo=on_lo)


def build_features(s: dict, dec: np.ndarray) -> pd.DataFrame:
    """Causal feature block. Every window ends at the decision second."""
    c = s["close"]; hi = s["high"]; lo = s["low"]; v = s["vol"]
    ct = c / TICK
    d1 = np.diff(ct, prepend=ct[0])

    csq = np.cumsum(d1 ** 2)
    cabs = np.cumsum(np.abs(d1))
    cup = np.cumsum((d1 > 0).astype(float))
    cv = np.cumsum(v)
    pv = np.cumsum(c * v)
    vwap = np.where(cv > 0, pv / np.maximum(cv, 1e-9), c)

    def win(w):
        return np.maximum(dec - w, 0)

    def ret(w):
        return ct[dec] - ct[win(w)]

    def rv(w):
        j = win(w)
        return np.sqrt((csq[dec] - csq[j]) / np.maximum(dec - j, 1))

    def eff(w):
        j = win(w)
        tot = cabs[dec] - cabs[j]
        return np.where(tot > 0, np.abs(ct[dec] - ct[j]) / np.maximum(tot, 1e-9), 0.0)

    def upf(w):
        j = win(w)
        return (cup[dec] - cup[j]) / np.maximum(dec - j, 1)

    def volsum(w):
        j = win(w)
        return cv[dec] - cv[j]

    def rng_pos(w):
        out = np.empty(len(dec))
        for m, i in enumerate(dec):
            a = max(i - w, 0)
            h = hi[a:i + 1].max(); l = lo[a:i + 1].min()
            out[m] = (c[i] - l) / (h - l) if h > l else 0.5
        return out

    rv900 = np.maximum(rv(900), 1e-6)
    or_hi = float(hi[:60].max()); or_lo = float(lo[:60].min())

    f = pd.DataFrame(index=np.arange(len(dec)))
    for w in (10, 30, 60, 300, 900, 1800):
        f[f"r{w}"] = ret(w)
        f[f"r{w}_n"] = ret(w) / rv900
    for w in (60, 300, 900):
        f[f"rv{w}"] = rv(w)
    f["rv_ratio"] = rv(60) / rv900
    for w in (300, 900, 3600):
        f[f"pos{w}"] = rng_pos(w)
        f[f"eff{w}"] = eff(w)
        f[f"upf{w}"] = upf(w)
    f["pos_day"] = rng_pos(10 ** 6)
    f["d_vwap"] = (c[dec] - vwap[dec]) / TICK
    f["d_vwap_n"] = f["d_vwap"] / rv900
    f["d_orhi"] = (c[dec] - or_hi) / TICK / rv900
    f["d_orlo"] = (c[dec] - or_lo) / TICK / rv900
    f["or_w"] = (or_hi - or_lo) / TICK
    f["d_onhi"] = (c[dec] - s["on_hi"]) / TICK / rv900
    f["d_onlo"] = (c[dec] - s["on_lo"]) / TICK / rv900
    f["tod"] = dec / 60.0
    base = np.maximum(volsum(3600), 1.0)
    for w in (60, 300, 900):
        tot = volsum(w)
        f[f"v{w}"] = tot
        f[f"v{w}_r"] = tot / (base * (w / 3600.0))
    return f


def label_side(s: dict, dec: np.ndarray, k: int, side: int) -> np.ndarray:
    """Realised R of a trade opened at the next second's open.

    side = +1 long, -1 short. Barriers sit k ticks either way, so R is +1, -1,
    or the mark-to-market fraction at timeout. Cost is applied downstream.
    """
    op = s["open"]; hi = s["high"]; lo = s["low"]; c = s["close"]; n = s["n"]
    out = np.full(len(dec), np.nan)
    kk = k * TICK
    INF = 1 << 30
    for m, i in enumerate(dec):
        e = i + 1
        if e >= n:
            continue
        entry = op[e]
        tp = entry + side * kk
        sl = entry - side * kk
        j = min(e + TIMEOUT_S, n - 1)
        h = hi[e:j + 1]; l = lo[e:j + 1]
        if side > 0:
            m_tp = h >= tp; m_sl = l <= sl
        else:
            m_tp = l <= tp; m_sl = h >= sl
        i_tp = int(np.argmax(m_tp)) if m_tp.any() else INF
        i_sl = int(np.argmax(m_sl)) if m_sl.any() else INF
        if i_tp == INF and i_sl == INF:
            out[m] = side * (c[j] - entry) / kk
        elif i_sl <= i_tp:
            out[m] = -1.0
        else:
            out[m] = 1.0
    return out


def main() -> None:
    print("loading 1s bars ...", flush=True)
    bars = load_bars()
    groups = dict(tuple(bars.groupby("session", sort=True)))
    print(f"{len(groups)} sessions, {len(bars):,} bars", flush=True)

    rows = []
    for sess in track(sorted(groups), label="features+labels"):
        s = session_grid(groups[sess])
        if not s:
            continue
        hi_sec = min(DEC_TO_SEC, s["n"] - TIMEOUT_S - 2)
        if hi_sec <= DEC_FROM_SEC:
            continue
        dec = np.arange(DEC_FROM_SEC, hi_sec, GRID_S)
        f = build_features(s, dec)
        f.insert(0, "session", pd.Timestamp(sess))
        f.insert(1, "sec", dec)
        for k in BRACKETS:
            f[f"R_long_{k}"] = label_side(s, dec, k, +1)
            f[f"R_short_{k}"] = label_side(s, dec, k, -1)
        rows.append(f)

    df = pd.concat(rows, ignore_index=True)
    before = len(df)
    df = df.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
    out = C.DATA / "features" / "rth_ml_dataset.parquet"
    df.to_parquet(out, index=False)
    print(f"\ndataset {df.shape} (dropped {before - len(df)}) -> {out}", flush=True)
    print(df.groupby(df.session.dt.strftime('%Y-%m')).size().to_string())
    for k in BRACKETS:
        for side in ("long", "short"):
            col = f"R_{side}_{k}"
            print(f"{col}: mean R {df[col].mean():+.4f}  "
                  f"WR {(df[col] > 0).mean():.4f}  n {len(df)}")


if __name__ == "__main__":
    main()
