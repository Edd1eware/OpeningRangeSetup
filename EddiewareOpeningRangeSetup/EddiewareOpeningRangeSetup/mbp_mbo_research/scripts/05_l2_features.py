"""L2 / order-flow features for every OR breakout event, from mbp-10 and mbo.

NO-LOOKAHEAD CONTRACT
---------------------
Every feature is computed from records with ts_event STRICTLY BEFORE the event's
signal_ts. Nothing that happens at or after the signal bar may enter a feature.
A single `<=` here is what turns an honest ~0 edge into a fake PF of 3.
"""
from __future__ import annotations

import sys
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA
from progress import track

TICK = 0.25
LOOKBACK_S = 60                   # order-flow window ending at signal_ts
EVENTS = DATA / "events" / "or_events.parquet"
OUT = DATA / "features"


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = db.DBNStore.from_file(path).to_df(price_type="float", tz="UTC")
    return df.reset_index() if not df.empty else df


def book_features(mbp: pd.DataFrame, ts) -> dict:
    """Top-of-book / depth state from the last mbp-10 update before `ts`."""
    pre = mbp[mbp.ts_event < ts]
    if pre.empty:
        return {}
    snap = pre.iloc[-1]
    out: dict[str, float] = {}

    bid_sz = np.array([snap.get(f"bid_sz_{i:02d}", np.nan) for i in range(10)], float)
    ask_sz = np.array([snap.get(f"ask_sz_{i:02d}", np.nan) for i in range(10)], float)
    bid_px = np.array([snap.get(f"bid_px_{i:02d}", np.nan) for i in range(10)], float)
    ask_px = np.array([snap.get(f"ask_px_{i:02d}", np.nan) for i in range(10)], float)

    out["spread_ticks"] = (ask_px[0] - bid_px[0]) / TICK
    out["mid"] = (ask_px[0] + bid_px[0]) / 2
    for n in (1, 3, 5, 10):
        b, a = np.nansum(bid_sz[:n]), np.nansum(ask_sz[:n])
        out[f"depth_bid_{n}"] = b
        out[f"depth_ask_{n}"] = a
        out[f"imb_{n}"] = (b - a) / (b + a) if (b + a) else 0.0
    # how fast depth thins out with distance: steep book = thin liquidity behind
    out["slope_bid"] = np.nansum(bid_sz[:5]) / max(np.nansum(bid_sz[5:]), 1.0)
    out["slope_ask"] = np.nansum(ask_sz[:5]) / max(np.nansum(ask_sz[5:]), 1.0)

    win = pre[pre.ts_event >= ts - pd.Timedelta(seconds=LOOKBACK_S)]
    if not win.empty:
        b1 = win.bid_sz_00.astype(float)
        a1 = win.ask_sz_00.astype(float)
        imb = (b1 - a1) / (b1 + a1).replace(0, np.nan)
        out["imb1_mean_60s"] = imb.mean()
        out["imb1_std_60s"] = imb.std()
        out["quote_updates_60s"] = len(win)
        out["depth1_trend"] = (b1.iloc[-1] + a1.iloc[-1]) / max((b1 + a1).mean(), 1.0)
    return out


def flow_features(mbo: pd.DataFrame, ts, side: int, or_level: float) -> dict:
    """Aggression, cancel pressure and queue state before the breakout."""
    pre = mbo[mbo.ts_event < ts]
    if pre.empty:
        return {}
    win = pre[pre.ts_event >= ts - pd.Timedelta(seconds=LOOKBACK_S)]
    out: dict[str, float] = {}

    trades = win[win.action == "T"]
    buy = trades.loc[trades.side == "A", "size"].sum()   # lifted the offer
    sell = trades.loc[trades.side == "B", "size"].sum()
    out["aggr_buy_60s"] = float(buy)
    out["aggr_sell_60s"] = float(sell)
    out["aggr_imb_60s"] = (buy - sell) / (buy + sell) if (buy + sell) else 0.0
    out["trade_count_60s"] = len(trades)
    out["trade_size_mean"] = float(trades["size"].mean()) if len(trades) else 0.0
    out["trade_size_max"] = float(trades["size"].max()) if len(trades) else 0.0

    adds = int((win.action == "A").sum())
    cancels = int((win.action == "C").sum())
    out["add_rate_60s"] = adds
    out["cancel_rate_60s"] = cancels
    out["cancel_per_add"] = cancels / adds if adds else 0.0
    out["cancel_per_trade"] = cancels / len(trades) if len(trades) else 0.0

    # cumulative delta since the open, strictly up to the signal
    alltr = pre[pre.action == "T"]
    cvd = (alltr.loc[alltr.side == "A", "size"].sum()
           - alltr.loc[alltr.side == "B", "size"].sum())
    out["cvd_since_open"] = float(cvd)
    out["cvd_aligned"] = float(cvd) * side      # positive = flow backs the break

    # resting size sitting at the level about to be broken
    at_level = win[(win.action.isin(["A", "C"]))
                   & (np.abs(win.price - or_level) < TICK / 2)]
    out["level_add_size"] = float(at_level.loc[at_level.action == "A", "size"].sum())
    out["level_cancel_size"] = float(at_level.loc[at_level.action == "C", "size"].sum())
    out["level_pulled"] = out["level_cancel_size"] - out["level_add_size"]
    return out


def main() -> int:
    if not EVENTS.exists():
        print(f"no events at {EVENTS}. run 04_or_events.py first.")
        return 1
    ev = pd.read_parquet(EVENTS)
    # features depend only on (session, or_minutes): one row per signal, not per bracket
    sigs = ev.drop_duplicates(["session", "or_minutes"])[
        ["session", "or_minutes", "side", "signal_ts", "or_high", "or_low"]]
    print(f"{len(sigs):,} unique signals over {sigs.session.nunique()} sessions")
    OUT.mkdir(parents=True, exist_ok=True)

    rows, missing = [], {"mbp-10": 0, "mbo": 0}
    for sess, grp in track(list(sigs.groupby("session")), label="L2 features"):
        mbp = _read(DATA / "mbp10" / f"NQ_mbp-10_{sess}.dbn.zst")
        mbo = _read(DATA / "mbo" / f"NQ_mbo_{sess}.dbn.zst")
        missing["mbp-10"] += mbp.empty
        missing["mbo"] += mbo.empty
        for r in grp.itertuples(index=False):
            ts = pd.Timestamp(r.signal_ts)
            level = r.or_high if r.side > 0 else r.or_low
            feat = {"session": sess, "or_minutes": r.or_minutes,
                    "has_mbp10": not mbp.empty, "has_mbo": not mbo.empty}
            if not mbp.empty:
                feat.update(book_features(mbp, ts))
            if not mbo.empty:
                feat.update(flow_features(mbo, ts, r.side, level))
            rows.append(feat)

    df = pd.DataFrame(rows)
    df.to_parquet(OUT / "l2_features.parquet", index=False)
    print(f"\n{len(df):,} rows x {df.shape[1]} cols -> {OUT/'l2_features.parquet'}")
    print(f"sessions without mbp-10: {missing['mbp-10']}, without mbo: {missing['mbo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
