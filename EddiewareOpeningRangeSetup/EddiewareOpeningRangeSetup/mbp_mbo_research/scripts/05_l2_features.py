"""Order-flow and footprint features for every OR signal, from MBO (and MBP-10).

NO-LOOKAHEAD CONTRACT
---------------------
Every feature comes from records strictly BEFORE the entry timestamp. The
breaking M1 candle itself is fair game: it closed before the entry. Anything at
or after the entry bar is not. One `<=` in the wrong place is what turns an
honest ~0 edge into a PF of 3.

FOOTPRINT IMBALANCE (ATAS convention)
-------------------------------------
ATAS compares volume DIAGONALLY, not across the same price:
  buy  imbalance at price P : ask_vol[P]  >= ratio * bid_vol[P - 1 tick]
  sell imbalance at price P : bid_vol[P]  >= ratio * ask_vol[P + 1 tick]
with a minimum volume so one lot against zero does not count.

AGGRESSOR SIDE - VERIFIED, NOT ASSUMED
In Databento MBO, `side` is the side that INITIATES the event, so for a trade:
  side 'A' = SELL aggressor (hits the bid) -> counts as BID volume
  side 'B' = BUY  aggressor (lifts the ask) -> counts as ASK volume
This is the opposite of the intuitive reading and it was wrong here at first.
Checked empirically on 300 buckets of 30s over the 5 MBO sessions:
  corr(size[A] - size[B], price change) = -0.700
  corr(size[B] - size[A], price change) = +0.700
Getting this backwards flips CVD, the delta and every imbalance, so the model
would have been fed the exact negative of the real order flow.
"""
from __future__ import annotations

import sys
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA, NY
from progress import track

TICK = 0.25
LOOKBACK_S = 60              # order-flow window ending at the entry
# Footprint geometry, DERIVED from the trader's own ATAS chart of 2026-10-09
# 09:36 and reproduced cell for cell from Databento `trades` (20 of the 23 rows
# matched as exact bid x ask pairs; the 3 that did not were misreadings of the
# screenshot, and Databento's values were the right ones).
IMB_MODE = "diag"            # ATAS's documented diagonal
IMB_RATIO = 3.0              # his ATAS "Imbalance Ratio" = 3, confirmed from the
                             # indicator settings. Recovered independently from
                             # the chart first: at 3.5 the blue level (3.09)
                             # would stop being flagged.
IMB_MIN_VOL = 70             # his ATAS "Volume filter". Recovering it from the
                             # chart gave a 30-100 range; he then confirmed the
                             # setting reads 70, which sits inside it.
IMB_MIN_DIFF = 0             # his ATAS "Minimum difference": no extra absolute
                             # gap required on top of the ratio.
IMB_GROUP = 5                # ticks per footprint row (1.25 index points)
IMB_GROUP_OFF = 1            # row boundary offset, in ticks
EVENTS = DATA / "events" / "or_events.parquet"
OUT = DATA / "features"


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = db.DBNStore.from_file(path).to_df(price_type="float", tz="UTC")
    if df.empty:
        return df
    df = df.reset_index()
    df["ts_ny"] = df.ts_event.dt.tz_convert(NY)
    # DBN ships `size` as uint64: any subtraction on it wraps around instead of
    # going negative, which silently turns a delta into ~1.8e19.
    if "size" in df.columns:
        df["size"] = df["size"].astype("int64")
    return df


def footprint(trades: pd.DataFrame, group: int = 1,
              offset: int = 0) -> pd.DataFrame:
    """bid/ask volume per price level from MBO trade records.

    `group` is ATAS's price grouping: how many ticks share one footprint row,
    and `offset` shifts where the row boundaries fall. Both were recovered by
    matching his chart: 5 ticks per row, offset 1.
    It matters more than it looks. The 09:30-09:31 NQ candle spans 118-204
    ticks, so ungrouped it has 118-204 rows holding a median of 6-28 contracts
    each, while the trader's chart shows 23 rows holding up to 294. Same data,
    different row height: his rows are roughly 5-9 ticks. Any absolute minimum
    volume threshold is meaningless until the grouping matches his.
    """
    if trades.empty:
        return pd.DataFrame(columns=["price", "bid_vol", "ask_vol"])
    t = trades.copy()
    t["lvl"] = ((np.round(t.price / TICK).astype("int64") - int(offset))
                // int(group))
    piv = (t.pivot_table(index="lvl", columns="side", values="size",
                         aggfunc="sum", fill_value=0)
             .reindex(columns=["A", "B"], fill_value=0)
             .rename(columns={"A": "bid_vol", "B": "ask_vol"}))
    return piv.sort_index()


def imbalance_features(fp: pd.DataFrame, side: int, or_level: float,
                       mode: str = "diag", group: int = 1) -> dict:
    """Count imbalances, how they stack, and where they sit.

    Two readings, both computed so the data can decide between them:

    mode="level" (the trader's reading, the default): compare the two numbers
      printed at the SAME price. The footprint shows `bid x ask`, so
        bid >= ratio * ask  -> the sell won that price
        ask >= ratio * bid  -> the buy won it
      In the example given: 107 x 55 is a sell win, 139 x 294 a buy win.

    mode="diag" (the default, and what the trader uses): the diagonal exactly as
      ATAS documents it, a price against the row below it:
        ask[P] >= ratio * bid[P - 1 tick]  -> buy imbalance
        bid[P] >= ratio * ask[P + 1 tick]  -> sell imbalance
      Verified against his chart's 09:36 candle on 2026-10-09, where exactly two
      rows were coloured, with the footprint rebuilt from Databento `trades`:
        139 x 294 -> buy,  294 / 95 = 3.09
        107 x  35 -> sell, 107 / 29 = 3.69
      and, with the minimum volume applied, nothing else. Rows at the top and
      bottom of the candle have no reference row and are skipped.

    bid volume is sell-aggressor volume and ask volume is buy-aggressor volume
    (see the module docstring: this was verified, not assumed).
    """
    out = {"imb_buy_n": 0, "imb_sell_n": 0, "imb_stacked_max": 0,
           "imb_aligned_n": 0, "imb_at_level": 0, "imb_max_ratio": 0.0,
           "fp_levels": len(fp), "fp_delta": 0.0, "fp_volume": 0.0}
    if fp.empty:
        return out

    ask = fp.ask_vol.to_dict()
    bid = fp.bid_vol.to_dict()
    out["fp_delta"] = float(fp.ask_vol.sum() - fp.bid_vol.sum())
    out["fp_volume"] = float(fp.ask_vol.sum() + fp.bid_vol.sum())
    level_lvl = (int(round(or_level / TICK)) - IMB_GROUP_OFF) // int(group)

    lo_lvl, hi_lvl = int(fp.index.min()), int(fp.index.max())
    buys, sells, ratios = [], [], []
    for lvl in fp.index:
        a_here, b_here = ask.get(lvl, 0), bid.get(lvl, 0)
        if mode == "level":
            a_ref, b_ref = b_here, a_here          # same price, the other column
            a_ok = b_ok = True
        else:
            # diagonal, in the direction that reproduces the trader's own chart
            a_ref, b_ref = bid.get(lvl - 1, 0), ask.get(lvl + 1, 0)
            # the top and bottom prices have no reference level: skip them
            # instead of comparing against a zero and flagging everything
            a_ok, b_ok = lvl < hi_lvl, lvl > lo_lvl
        if (a_ok and a_here >= IMB_MIN_VOL
                and a_here - a_ref >= IMB_MIN_DIFF
                and a_here >= IMB_RATIO * max(a_ref, 1)):
            buys.append(lvl)
            ratios.append(a_here / max(a_ref, 1))
        if (b_ok and b_here >= IMB_MIN_VOL
                and b_here - b_ref >= IMB_MIN_DIFF
                and b_here >= IMB_RATIO * max(b_ref, 1)):
            sells.append(lvl)
            ratios.append(b_here / max(b_ref, 1))

    out["imb_buy_n"] = len(buys)
    out["imb_sell_n"] = len(sells)
    out["imb_max_ratio"] = round(max(ratios), 2) if ratios else 0.0
    aligned = buys if side > 0 else sells
    out["imb_aligned_n"] = len(aligned)
    # stacked = consecutive price levels, which is what ATAS highlights
    run = best = 0
    for i, lvl in enumerate(sorted(aligned)):
        run = run + 1 if i and lvl == sorted(aligned)[i - 1] + 1 else 1
        best = max(best, run)
    out["imb_stacked_max"] = best
    out["imb_at_level"] = int(any(abs(l - level_lvl) <= 2 for l in aligned))
    return out


def flow_features(mbo: pd.DataFrame, t_entry, side: int, or_level: float) -> dict:
    """Aggression, cancel pressure and CVD, all strictly before the entry."""
    pre = mbo[mbo.ts_event < t_entry]
    if pre.empty:
        return {}
    win = pre[pre.ts_event >= t_entry - pd.Timedelta(seconds=LOOKBACK_S)]
    out: dict[str, float] = {}

    trades = win[win.action == "T"]
    buy = float(trades.loc[trades.side == "B", "size"].sum())   # lifted the ask
    sell = float(trades.loc[trades.side == "A", "size"].sum())  # hit the bid
    out["aggr_buy_60s"] = buy
    out["aggr_sell_60s"] = sell
    out["aggr_imb_60s"] = (buy - sell) / (buy + sell) if (buy + sell) else 0.0
    out["aggr_aligned_60s"] = (buy - sell) * side
    out["trade_count_60s"] = len(trades)
    out["trade_size_mean"] = float(trades["size"].mean()) if len(trades) else 0.0
    out["trade_size_max"] = float(trades["size"].max()) if len(trades) else 0.0

    adds = int((win.action == "A").sum())
    cancels = int((win.action == "C").sum())
    out["add_rate_60s"] = adds
    out["cancel_rate_60s"] = cancels
    out["cancel_per_add"] = cancels / adds if adds else 0.0
    out["cancel_per_trade"] = cancels / len(trades) if len(trades) else 0.0

    all_tr = pre[pre.action == "T"]
    cvd = float(all_tr.loc[all_tr.side == "B", "size"].sum()
                - all_tr.loc[all_tr.side == "A", "size"].sum())
    out["cvd_since_open"] = cvd
    out["cvd_aligned"] = cvd * side

    at_level = win[win.action.isin(["A", "C"])
                   & (np.abs(win.price - or_level) < TICK / 2)]
    out["level_add_size"] = float(at_level.loc[at_level.action == "A", "size"].sum())
    out["level_cancel_size"] = float(at_level.loc[at_level.action == "C", "size"].sum())
    out["level_pulled"] = out["level_cancel_size"] - out["level_add_size"]
    return out


def book_features(mbp: pd.DataFrame, t_entry) -> dict:
    """Depth state from the last MBP-10 update before the entry."""
    pre = mbp[mbp.ts_event < t_entry]
    if pre.empty:
        return {}
    snap = pre.iloc[-1]
    out: dict[str, float] = {}
    bid_sz = np.array([snap.get(f"bid_sz_{i:02d}", np.nan) for i in range(10)], float)
    ask_sz = np.array([snap.get(f"ask_sz_{i:02d}", np.nan) for i in range(10)], float)
    out["spread_ticks"] = (float(snap.get("ask_px_00", np.nan))
                           - float(snap.get("bid_px_00", np.nan))) / TICK
    for n in (1, 3, 5, 10):
        b, a = np.nansum(bid_sz[:n]), np.nansum(ask_sz[:n])
        out[f"depth_bid_{n}"] = b
        out[f"depth_ask_{n}"] = a
        out[f"imb_book_{n}"] = (b - a) / (b + a) if (b + a) else 0.0
    out["slope_bid"] = np.nansum(bid_sz[:5]) / max(np.nansum(bid_sz[5:]), 1.0)
    out["slope_ask"] = np.nansum(ask_sz[:5]) / max(np.nansum(ask_sz[5:]), 1.0)
    return out


def main() -> int:
    if not EVENTS.exists():
        print(f"no events at {EVENTS}. run 04_or_events.py first.")
        return 1
    ev = pd.read_parquet(EVENTS)
    # features depend only on the signal, not on the bracket or the entry mode
    sigs = ev.drop_duplicates("session")[
        ["session", "side", "signal_minute_ny", "or_high", "or_low"]]
    print(f"{len(sigs):,} signals, one per session")
    OUT.mkdir(parents=True, exist_ok=True)

    rows, have_mbo, have_mbp = [], 0, 0
    for r in track(list(sigs.itertuples(index=False)), label="L2 features"):
        sess = r.session
        mbo = _read(DATA / "mbo" / f"NQ_mbo_{sess}.dbn.zst")
        mbp = _read(DATA / "mbp10" / f"NQ_mbp-10_{sess}.dbn.zst")
        have_mbo += not mbo.empty
        have_mbp += not mbp.empty

        minute_start = pd.Timestamp(r.signal_minute_ny)
        minute_end = minute_start + pd.Timedelta(minutes=1)
        t_entry = minute_end.tz_convert("UTC")
        level = r.or_high if r.side > 0 else r.or_low

        feat = {"session": sess, "has_mbo": not mbo.empty, "has_mbp10": not mbp.empty}
        if not mbo.empty:
            # footprint of the breaking candle only: it closed before the entry
            candle = mbo[(mbo.ts_ny >= minute_start) & (mbo.ts_ny < minute_end)
                         & (mbo.action == "T")]
            feat.update(imbalance_features(footprint(candle, IMB_GROUP,
                                                     IMB_GROUP_OFF), r.side,
                                           level, mode=IMB_MODE, group=IMB_GROUP))
            feat.update(flow_features(mbo, t_entry, r.side, level))
        if not mbp.empty:
            feat.update(book_features(mbp, t_entry))
        rows.append(feat)

    df = pd.DataFrame(rows)
    df.to_parquet(OUT / "l2_features.parquet", index=False)
    print(f"\n{len(df):,} rows x {df.shape[1]} cols -> {OUT/'l2_features.parquet'}")
    print(f"sessions with MBO: {have_mbo}/{len(sigs)}, "
          f"with MBP-10: {have_mbp}/{len(sigs)}")
    if have_mbo:
        cols = [c for c in ("imb_aligned_n", "imb_stacked_max", "imb_at_level",
                            "fp_delta", "cvd_aligned", "cancel_per_trade")
                if c in df.columns]
        print("\nfootprint / flow summary (sessions with MBO):")
        print(df.loc[df.has_mbo, cols].describe().round(2).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
