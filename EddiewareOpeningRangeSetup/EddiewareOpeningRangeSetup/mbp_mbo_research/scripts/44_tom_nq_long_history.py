"""Turn of month on NQ FUTURES themselves, 26 years, free, right now.

Note 06 replicated the effect on SPY, QQQ, DIA and IWM. Those are ETFs on
other indices; the instrument that will actually be traded is NQ futures, and
its daily history is free and goes back to 2000. That is 6,582 sessions and
roughly a thousand days inside the +1..+3 window, available without waiting
for the Databento download and without spending anything.

Daily bars cannot resolve a 300-tick intraday bracket -- that still needs the
1-second path and script 41. What they CAN settle is whether the anomaly is
present in this instrument at all, over a span where luck is not an
explanation, before any money or compute goes into the bracket version.

Also tested here, and declared before running: a MECHANISM.

    If the effect comes from month-end and month-start institutional flows --
    pension rebalancing and retirement contributions -- then it should be
    STRONGER after a month in which equities fell, because a balanced fund
    that has drifted underweight equities has to buy them back. That is an
    economic prediction with a direction, not a conditioning variable picked
    because it looked good. If the effect is instead uniform across prior-month
    signs, the flow story is wrong even if the effect is real.

Instruments: NQ=F is primary, the rest are context. ^GSPC is included for its
length, with a guard: Yahoo's pre-1962 rows carry the close repeated as the
open, which makes an open-to-close return identically zero, so those rows are
dropped rather than silently averaged in.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

SYMBOLS = ("NQ=F", "ES=F", "YM=F", "^NDX", "^GSPC")
PRIMARY = "NQ=F"
SEED = 20261013


def fetch(sym: str) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(sym, start="1900-01-01", auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise RuntimeError("empty")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    d = df.reset_index().rename(columns=str.lower)
    d = d[["date", "open", "high", "low", "close"]].dropna()
    d["date"] = pd.to_datetime(d.date)
    # a row whose open equals its close to the cent is a synthetic open, which
    # Yahoo carries for old index history; an open-to-close return built on it
    # is identically zero and would dilute everything
    synth = (d.open - d.close).abs() < 1e-9
    if synth.mean() > 0.2:
        d = d.loc[~synth]
    return d.sort_values("date").reset_index(drop=True)


def mark(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["year"] = d.date.dt.year
    d["month"] = d.date.dt.month
    g = d.groupby([d.year, d.month])
    d["tdom"] = g.cumcount() + 1
    d["tdom_rev"] = g.cumcount(ascending=False) + 1
    d["is_last"] = d.tdom_rev == 1
    d["tom_pos"] = np.where(d.is_last, "last",
                            np.where(d.tdom <= 3, "+" + d.tdom.astype(str), ""))
    d["tom3"] = d.tom_pos.isin(["+1", "+2", "+3"])
    d["classic"] = d.tom_pos != ""
    d["placebo"] = d.tom3.shift(6, fill_value=False)
    d["r_oc"] = (d.close / d.open - 1.0) * 100
    d["decade"] = (d.year // 10) * 10
    # prior calendar month's return, close of last day to close of last day
    mclose = d.groupby([d.year, d.month]).close.last()
    mret = mclose.pct_change() * 100
    key = pd.MultiIndex.from_arrays([d.year, d.month])
    d["prev_month_ret"] = mret.shift(1).reindex(key).to_numpy()
    return d


def test(d, mask, label, sym, rows):
    a = d.loc[mask, "r_oc"].dropna().to_numpy()
    b = d.loc[~mask, "r_oc"].dropna().to_numpy()
    if len(a) < 30:
        return
    t, p = stats.ttest_ind(a, b, equal_var=False)
    se = a.std(ddof=1) / np.sqrt(len(a))
    rows.append(dict(symbol=sym, scope=label, n=len(a),
                     mean_pct=float(a.mean()), rest_pct=float(b.mean()),
                     t=float(t), p=float(p), wr=float((a > 0).mean()),
                     lo95=float(a.mean() - 1.96 * se),
                     hi95=float(a.mean() + 1.96 * se)))
    print(f"  {label:30} n {len(a):5} mean {a.mean():+.4f}%  rest {b.mean():+.4f}%  "
          f"t {t:+.2f}  p {p:.4f}  WR {(a>0).mean():.4f}")


def main():
    rows, mech = [], []
    frames = {}
    for sym in SYMBOLS:
        try:
            d = mark(fetch(sym))
        except Exception as exc:
            print(f"{sym}: {exc}")
            continue
        frames[sym] = d
        print(f"\n################ {sym}  {len(d)} sessions "
              f"{d.date.min().date()}..{d.date.max().date()} ################")
        test(d, d.tom3, "window +1..+3", sym, rows)
        test(d, d.classic, "classic incl. last day", sym, rows)
        test(d, d.is_last, "last day of month alone", sym, rows)
        test(d, d.placebo, "PLACEBO +6 trading days", sym, rows)

        print("  --- by decade, window +1..+3 ---")
        dec = []
        for decade, g in d.groupby("decade"):
            x = g.loc[g.tom3, "r_oc"].dropna().to_numpy()
            if len(x) < 30:
                continue
            se = x.std(ddof=1) / np.sqrt(len(x))
            dec.append(dict(decade=int(decade), n=len(x),
                            mean_pct=round(float(x.mean()), 4),
                            t=round(float(x.mean() / se), 3),
                            wr=round(float((x > 0).mean()), 4)))
        if dec:
            print(pd.DataFrame(dec).to_string(index=False))

        # the mechanism test
        sub = d.loc[d.tom3 & d.prev_month_ret.notna()]
        dn = sub.loc[sub.prev_month_ret < 0, "r_oc"].to_numpy()
        up = sub.loc[sub.prev_month_ret >= 0, "r_oc"].to_numpy()
        if len(dn) >= 30 and len(up) >= 30:
            t, p = stats.ttest_ind(dn, up, equal_var=False)
            print(f"  --- mechanism: after a DOWN month vs an UP month ---")
            print(f"  after DOWN  n {len(dn):5} mean {dn.mean():+.4f}%  WR {(dn>0).mean():.4f}")
            print(f"  after UP    n {len(up):5} mean {up.mean():+.4f}%  WR {(up>0).mean():.4f}")
            print(f"  difference  t {t:+.2f}  p {p:.4f}  "
                  f"-> {'supports the flow story' if (t > 0 and p < 0.05) else 'does not support it'}")
            mech.append(dict(symbol=sym, n_down=len(dn), n_up=len(up),
                             mean_down=float(dn.mean()), mean_up=float(up.mean()),
                             wr_down=float((dn > 0).mean()), wr_up=float((up > 0).mean()),
                             t=float(t), p=float(p)))

    out = pd.DataFrame(rows)
    out.to_csv(C.DATA / "reports" / "tom_nq_long_history.csv", index=False)
    pd.DataFrame(mech).to_csv(C.DATA / "reports" / "tom_mechanism.csv", index=False)

    print("\n=== summary, window +1..+3, Bonferroni over the instruments ===")
    s = out[out.scope == "window +1..+3"]
    print(s[["symbol", "n", "mean_pct", "rest_pct", "t", "p", "wr"]].round(4).to_string(index=False))
    a = 0.05 / max(len(s), 1)
    print(f"alpha {a:.4f}; significant: {int((s.p < a).sum())} of {len(s)}")
    pr = s[s.symbol == PRIMARY]
    if len(pr):
        print(f"\nPRIMARY {PRIMARY}: n {int(pr.n.iloc[0])}, mean "
              f"{pr.mean_pct.iloc[0]:+.4f}% vs rest {pr.rest_pct.iloc[0]:+.4f}%, "
              f"p {pr.p.iloc[0]:.4f}, WR {pr.wr.iloc[0]:.4f}")
    print(f"\nwrote tom_nq_long_history.csv and tom_mechanism.csv to {C.DATA/'reports'}")


if __name__ == "__main__":
    main()
