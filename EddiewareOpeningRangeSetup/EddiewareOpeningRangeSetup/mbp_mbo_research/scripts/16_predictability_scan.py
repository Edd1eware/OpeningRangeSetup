"""Step 1 of the pre-registered tape study: does aggressor imbalance predict
the next chunk of price at all, and with what sign?

This is deliberately NOT a strategy. It is one measurement with a trivial null
(slope = 0) and a very large n, whose job is to decide whether any order-flow
rule can clear the 1.8 tick cost, and if so whether the sign says continuation
or reversion. See notes_md/2026-10-12_PREREGISTRO_TAPE.md section 2.

Design
------
* Window 09:30-10:30 ET, 150 EDT 2026 sessions, tick-exact tape.
* Non-overlapping time buckets of B seconds, B in {5, 15, 30, 60}.
* Feature at bucket t: normalised signed aggressor imbalance,
      imb = (buy_vol - sell_vol) / (buy_vol + sell_vol)      in [-1, +1]
* Target: price change from the END of bucket t to the END of bucket t+1,
  in ticks. Strictly forward: nothing inside bucket t+1 enters the feature,
  and nothing after the end of bucket t enters the reference price.

The bid-ask bounce control
--------------------------
The naive reference price (last traded price of the bucket) is contaminated:
if the bucket's last trade was a buy aggressor, that price sits at the ask, so
the measured forward change inherits a mechanical pull back toward the mid.
That bias works AGAINST continuation and would masquerade as mean reversion.

So the primary estimator is a mid proxy taken at the end of each bucket:
    mid = (last buy-aggressor price + last sell-aggressor price) / 2
Both ends of the target use the SAME estimator, so the bounce largely cancels.
The naive last-trade estimator is reported beside it precisely to show how big
the artifact is. If the two disagree in sign, the naive one is the broken one.

Statistics
----------
* OLS slope of forward ticks on imb: the effect in TICKS per unit imbalance.
* Mean forward move conditional on the top/bottom decile of imb. This is the
  operationally meaningful number: it is what a rule that only fires on extreme
  imbalance would actually capture, and it gets compared against 1.8 ticks.
* Session-level block bootstrap (2000 draws, sessions resampled with
  replacement) because buckets inside one session are not independent.
* 4 bucket sizes x 2 estimators = 8 cells, so Bonferroni is 0.05/8 = 0.00625.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATA, NY  # noqa: E402
from progress import track  # noqa: E402

TAPE = DATA / "tape" / "tape_trades_2026.parquet"
OUT = DATA / "reports" / "predictability_scan.csv"

BUCKETS_S = (5, 15, 30, 60)
COST_TICKS = 1.8
N_BOOT = 2000
SEED = 20261012

# session clock window, seconds from 09:30:00 ET
WIN_FROM_S = 0            # 09:30:00
WIN_TO_S = 60 * 60        # 10:30:00


def load_tape() -> pd.DataFrame:
    t = pd.read_parquet(TAPE)
    ny = pd.to_datetime(t["ts_ns"], utc=True).dt.tz_convert(NY)
    secs = (ny.dt.hour * 3600 + ny.dt.minute * 60 + ny.dt.second
            + ny.dt.microsecond / 1e6) - 9.5 * 3600
    t["sec"] = secs.to_numpy()
    t = t[(t["sec"] >= WIN_FROM_S) & (t["sec"] < WIN_TO_S)]
    return t.reset_index(drop=True)


def bucket_table(t: pd.DataFrame, b: int) -> pd.DataFrame:
    """Aggregate the tape into non-overlapping b-second buckets per session."""
    d = t.copy()
    d["bkt"] = (d["sec"].to_numpy() // b).astype("int32")

    sz = d["size"].to_numpy().astype("int64")
    sign = d["sign"].to_numpy().astype("int64")
    d["buy_vol"] = np.where(sign > 0, sz, 0)
    d["sell_vol"] = np.where(sign < 0, sz, 0)

    g = d.groupby(["session", "bkt"], sort=True)
    agg = g.agg(
        buy_vol=("buy_vol", "sum"),
        sell_vol=("sell_vol", "sum"),
        n_trades=("size", "size"),
        last_px=("px_t", "last"),
    ).reset_index()

    # end-of-bucket mid proxy: last price on each aggressor side
    last_buy = (d[d["sign"] > 0].groupby(["session", "bkt"])["px_t"].last()
                .rename("last_buy_px"))
    last_sell = (d[d["sign"] < 0].groupby(["session", "bkt"])["px_t"].last()
                 .rename("last_sell_px"))
    agg = agg.merge(last_buy, on=["session", "bkt"], how="left")
    agg = agg.merge(last_sell, on=["session", "bkt"], how="left")

    mid = (agg["last_buy_px"] + agg["last_sell_px"]) / 2.0
    # if one side never traded in the bucket, fall back to the last trade
    agg["mid_px"] = mid.fillna(agg["last_px"].astype("float64"))

    tot = agg["buy_vol"] + agg["sell_vol"]
    agg["imb"] = np.where(tot > 0, (agg["buy_vol"] - agg["sell_vol"]) / tot, 0.0)
    return agg


def pairs(agg: pd.DataFrame, px_col: str) -> pd.DataFrame:
    """Feature at t, forward target from end of t to end of t+1. Same session,
    strictly adjacent buckets, both non-empty."""
    a = agg.sort_values(["session", "bkt"]).reset_index(drop=True)
    nxt_px = a.groupby("session")[px_col].shift(-1)
    nxt_bkt = a.groupby("session")["bkt"].shift(-1)
    ok = (nxt_bkt - a["bkt"]) == 1
    out = pd.DataFrame({
        "session": a["session"],
        "imb": a["imb"],
        "fwd": (nxt_px - a[px_col]),   # already in ticks: px_t is integer ticks
    })[ok & nxt_px.notna()]
    return out.reset_index(drop=True)


def boot_sessions(df: pd.DataFrame, stat, rng: np.random.Generator,
                  n_boot: int = N_BOOT) -> tuple[float, float]:
    """Block bootstrap: resample SESSIONS with replacement, recompute stat."""
    keys = df["session"].to_numpy()
    uniq = np.unique(keys)
    idx_by_key = {k: np.flatnonzero(keys == k) for k in uniq}
    vals = np.empty(n_boot, dtype="float64")
    for i in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by_key[k] for k in pick])
        vals[i] = stat(df.iloc[idx])
    return float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))


def slope(df: pd.DataFrame) -> float:
    x = df["imb"].to_numpy()
    y = df["fwd"].to_numpy()
    xc = x - x.mean()
    den = (xc * xc).sum()
    return float((xc * (y - y.mean())).sum() / den) if den > 0 else np.nan


def main() -> None:
    print("loading tape...", flush=True)
    t = load_tape()
    print(f"  {len(t):,} trades, {t['session'].nunique()} sessions, "
          f"09:30-10:30 ET", flush=True)

    rng = np.random.default_rng(SEED)
    rows: list[dict] = []

    cells = [(b, est) for b in BUCKETS_S for est in ("mid_px", "last_px")]
    for b, est in track(cells, label="predictability scan"):
        agg = bucket_table(t, b)
        p = pairs(agg, est)

        x = p["imb"].to_numpy()
        y = p["fwd"].to_numpy()

        sl = slope(p)
        lo, hi = boot_sessions(p, slope, rng)

        # operational effect: what an extreme-imbalance rule would capture
        hi_cut = np.quantile(x, 0.90)
        lo_cut = np.quantile(x, 0.10)
        top = y[x >= hi_cut]
        bot = y[x <= lo_cut]
        # directional effect in ticks: sign-aligned forward move on the extremes
        aligned = np.concatenate([top, -bot])
        eff = float(aligned.mean())
        eff_lo, eff_hi = boot_sessions(
            pd.DataFrame({"session": np.concatenate([
                p["session"].to_numpy()[x >= hi_cut],
                p["session"].to_numpy()[x <= lo_cut]]),
                "v": aligned}),
            lambda d: float(d["v"].mean()), rng)

        sp = float(pd.Series(x).corr(pd.Series(y), method="spearman"))

        rows.append(dict(
            bucket_s=b, estimator=est, n=len(p),
            slope_ticks=sl, slope_lo=lo, slope_hi=hi,
            spearman=sp,
            extreme_decile_ticks=eff, eff_lo=eff_lo, eff_hi=eff_hi,
            n_extreme=len(aligned),
            fwd_sd=float(y.std()),
        ))

    res = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT, index=False)

    print("", flush=True)
    print("=" * 78, flush=True)
    print("SLOPE of forward ticks on normalised aggressor imbalance", flush=True)
    print("(positive = continuation, negative = reversion)", flush=True)
    print("", flush=True)
    print("| bucket | estimador | n | pendiente ticks | IC95 bootstrap | spearman |",
          flush=True)
    print("|---|---|---|---|---|---|", flush=True)
    for r in rows:
        print(f"| {r['bucket_s']}s | {r['estimator']} | {r['n']:,} | "
              f"{r['slope_ticks']:+.3f} | "
              f"[{r['slope_lo']:+.3f}, {r['slope_hi']:+.3f}] | "
              f"{r['spearman']:+.4f} |", flush=True)

    print("", flush=True)
    print("EFFECT an extreme-decile rule would capture, in TICKS", flush=True)
    print(f"(compare against cost {COST_TICKS} ticks; "
          "pre-registered go/no-go is 0.5 ticks)", flush=True)
    print("", flush=True)
    print("| bucket | estimador | n extremos | efecto ticks | IC95 | "
          "¿supera 0.5? | ¿supera costo 1.8? |", flush=True)
    print("|---|---|---|---|---|---|---|", flush=True)
    for r in rows:
        print(f"| {r['bucket_s']}s | {r['estimator']} | {r['n_extreme']:,} | "
              f"{r['extreme_decile_ticks']:+.3f} | "
              f"[{r['eff_lo']:+.3f}, {r['eff_hi']:+.3f}] | "
              f"{'SI' if abs(r['extreme_decile_ticks']) >= 0.5 else 'no'} | "
              f"{'SI' if abs(r['extreme_decile_ticks']) >= COST_TICKS else 'no'} |",
              flush=True)

    print("", flush=True)
    mid = res[res.estimator == "mid_px"]
    print(f"wrote {OUT}", flush=True)
    print("", flush=True)
    print("PRIMARY READ (mid proxy, bounce-controlled):", flush=True)
    for r in mid.itertuples():
        sig = "CI excludes 0" if (r.eff_lo > 0) or (r.eff_hi < 0) else "CI includes 0"
        print(f"  {r.bucket_s:>2}s  effect {r.extreme_decile_ticks:+.3f} ticks  "
              f"slope {r.slope_ticks:+.3f}  {sig}", flush=True)


if __name__ == "__main__":
    main()
