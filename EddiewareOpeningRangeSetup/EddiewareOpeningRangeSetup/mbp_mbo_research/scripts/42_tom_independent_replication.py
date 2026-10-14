"""Independent replication of the turn-of-month effect, on data this project
has never touched and did not pay for.

The candidate in note 05 lives in 32 days of one partial year of NQ. Buying
more NQ history widens that sample but it is still the same instrument, the
same venue and the same era. A genuinely independent check asks whether the
anomaly exists at all in the underlying index over a span long enough that
luck cannot explain it.

SPY daily bars go back to 1993, which is about 400 month boundaries and well
over a thousand turn-of-month sessions, free. That cannot validate the
300-tick intraday bracket -- daily bars have no path -- but it answers the
prior question, which is the one that matters first:

    is the turn-of-month effect present in the S&P 500 open-to-close return,
    out of this project's sample, over three decades?

If it is not, the NQ number is 32 coin flips and the story written around it
was a story. If it is, the NQ test becomes a question about the BRACKET rather
than about the anomaly, which is a much better place to be.

Also reported, because the anomaly literature is old enough that decay is the
norm: the effect decade by decade. An effect that was strong in the nineties
and gone since is not tradeable now, and pooling thirty years would hide that.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

SYMBOLS = ("SPY", "QQQ")
START = "1993-01-01"
SEED = 20261013


def fetch(sym: str) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(sym, start=START, auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise SystemExit(f"no data for {sym}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    d = df.reset_index().rename(columns=str.lower)
    d = d[["date", "open", "high", "low", "close"]].dropna()
    d["date"] = pd.to_datetime(d.date)
    return d.sort_values("date").reset_index(drop=True)


def mark_tom(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["year"] = d.date.dt.year
    d["month"] = d.date.dt.month
    g = d.groupby([d.year, d.month])
    d["tdom"] = g.cumcount() + 1
    d["tdom_rev"] = g.cumcount(ascending=False) + 1
    d["is_last"] = d.tdom_rev == 1
    d["tom_pos"] = np.where(d.is_last, "last",
                            np.where(d.tdom <= 3, "+" + d.tdom.astype(str), ""))
    d["tom"] = d.tom_pos != ""
    # same shape of window, shifted five trading days forward: no calendar
    # story lives there, so it is the placebo
    d["placebo"] = d.tom.shift(5, fill_value=False)
    # open-to-close in percent, which is comparable across three decades of
    # very different price levels
    d["r_oc"] = (d.close / d.open - 1.0) * 100
    d["r_cc"] = d.close.pct_change() * 100
    d["decade"] = (d.year // 10) * 10
    return d


def block(d, mask, label, col="r_oc"):
    from scipy import stats
    a = d.loc[mask, col].dropna().to_numpy()
    b = d.loc[~mask, col].dropna().to_numpy()
    if len(a) < 30:
        return None
    t, p = stats.ttest_ind(a, b, equal_var=False)
    se = a.std(ddof=1) / np.sqrt(len(a))
    return dict(scope=label, n_in=len(a), n_out=len(b),
                mean_in_pct=float(a.mean()), mean_out_pct=float(b.mean()),
                diff_pct=float(a.mean() - b.mean()),
                t=float(t), p=float(p),
                lo95=float(a.mean() - 1.96 * se),
                hi95=float(a.mean() + 1.96 * se),
                wr_in=float((a > 0).mean()), wr_out=float((b > 0).mean()))


def main():
    rows = []
    for sym in SYMBOLS:
        print(f"\n################ {sym} ################", flush=True)
        try:
            d = mark_tom(fetch(sym))
        except Exception as exc:
            print(f"  fetch failed: {exc}")
            continue
        print(f"{len(d)} sessions, {d.date.min().date()} .. {d.date.max().date()}, "
              f"{int(d.tom.sum())} turn-of-month days")

        print("\n  --- open-to-close return, percent ---")
        for mask, label in ((d.tom, "turn of month"),
                            (d.placebo, "PLACEBO +5 trading days"),
                            (d.date.dt.dayofweek == 0, "Monday (control)")):
            r = block(d, mask, label)
            if r:
                r["symbol"] = sym
                rows.append(r)
                print(f"  {label:26} n {r['n_in']:5} mean_in {r['mean_in_pct']:+.4f}%  "
                      f"mean_out {r['mean_out_pct']:+.4f}%  diff {r['diff_pct']:+.4f}  "
                      f"t {r['t']:+.2f}  p {r['p']:.4f}  "
                      f"WR {r['wr_in']:.3f} vs {r['wr_out']:.3f}")

        print("\n  --- turn of month by decade (anomalies decay) ---")
        dec = []
        for decade, g in d.groupby("decade"):
            a = g.loc[g.tom, "r_oc"].dropna().to_numpy()
            b = g.loc[~g.tom, "r_oc"].dropna().to_numpy()
            if len(a) < 30:
                continue
            se = a.std(ddof=1) / np.sqrt(len(a))
            dec.append(dict(symbol=sym, decade=int(decade), n=len(a),
                            mean_in_pct=float(a.mean()), mean_out_pct=float(b.mean()),
                            t_vs_zero=float(a.mean() / se),
                            wr_in=float((a > 0).mean())))
        dd = pd.DataFrame(dec)
        if len(dd):
            print(dd.round(4).to_string(index=False))

        print("\n  --- by position in the window ---")
        pos = []
        for p_ in ("last", "+1", "+2", "+3"):
            a = d.loc[d.tom_pos.eq(p_), "r_oc"].dropna().to_numpy()
            if len(a) < 30:
                continue
            se = a.std(ddof=1) / np.sqrt(len(a))
            pos.append(dict(symbol=sym, position=p_, n=len(a),
                            mean_pct=float(a.mean()), t=float(a.mean() / se),
                            wr=float((a > 0).mean())))
        if pos:
            print(pd.DataFrame(pos).round(4).to_string(index=False))
            rows += pos

    out = pd.DataFrame(rows)
    out.to_csv(C.DATA / "reports" / "tom_independent_replication.csv", index=False)
    print(f"\nwrote {C.DATA / 'reports' / 'tom_independent_replication.csv'}")
    print("\nReading: a turn-of-month mean clearly above the non-tom mean with a "
          "clean placebo, present in the most recent decade, supports the NQ "
          "candidate. Present only before 2010 means the anomaly decayed and "
          "the NQ number is 32 coin flips.")


if __name__ == "__main__":
    main()
