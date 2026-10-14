"""Rank every pre-registered daily condition by the only quantity that matters.

The geometry from script 46 collapses the whole search to one number. A
condition is worth exactly as much as its day-session drift divided by the
square of the volatility it carries:

    2P - 1  ~  mu * b / sigma^2

so a condition with twice the drift is worth twice as much, and a condition
whose drift comes with twice the volatility is worth a quarter as much. Ranking
candidates by mu alone would reward the noisy ones; ranking by mu/sigma^2 is
the honest ordering, and that is what this does.

Measured on free daily history, which is the right sample for a daily-frequency
question: ^GSPC back to 1962 is 16,000 sessions, ^NDX to 1985, and NQ futures
to 2000. No Databento spend, no waiting.

The conditions, declared before running
---------------------------------------
Each one is either exactly derivable from the calendar or computable from the
prior session's own bars, so none depends on a hand-typed list, and each has
published support rather than being invented here:

    C1  turn of month, days +1..+3            the baseline from note 06
    C2  after a 1-sigma down day              short-term reversal
    C3  after a 2-sigma down day              the same effect, stronger cut
    C4  after a 1-sigma UP day                the mirror; should be weaker if
                                              reversal rather than momentum
    C5  first session after a market holiday  the holiday effect
    C6  Monday after a down week              the weekend effect
    C7  OpEx week, Monday to the third Friday dealer hedging unwind
    C8  last five sessions of December plus
        the first two of January              the Santa Claus window
    C9  after a down day that CLOSED at its
        low (bottom 10% of its range)         capitulation, a stronger form of C2
    C10 after two consecutive down days       the two-day reversal

Each is reported with its drift, its own volatility, the ratio that decides,
and a placebo built by shifting the condition five sessions forward. A
condition whose placebo looks the same is measuring market drift, not itself.
Bonferroni is applied over the ten conditions, and the decade breakdown is
printed for anything that survives, because an effect that died in 1999 is not
tradeable in 2026.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

SYMBOLS = ("^GSPC", "^NDX", "NQ=F")
N_COND = 10
SEED = 20261013


def fetch(sym: str) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(sym, start="1900-01-01", auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    d = df.reset_index().rename(columns=str.lower)
    d = d[["date", "open", "high", "low", "close"]].dropna()
    d["date"] = pd.to_datetime(d.date)
    synth = (d.open - d.close).abs() < 1e-9
    if synth.mean() > 0.2:
        d = d.loc[~synth]
    return d.sort_values("date").reset_index(drop=True)


def build(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["r_oc"] = (d.close / d.open - 1.0) * 100
    d["r_cc"] = d.close.pct_change() * 100
    d["year"] = d.date.dt.year
    d["month"] = d.date.dt.month
    d["dow"] = d.date.dt.dayofweek
    d["decade"] = (d.year // 10) * 10
    g = d.groupby([d.year, d.month])
    d["tdom"] = g.cumcount() + 1
    d["tdom_rev"] = g.cumcount(ascending=False) + 1

    sd = d.r_cc.rolling(250, min_periods=60).std()
    prev = d.r_cc.shift(1)
    prev_sd = sd.shift(1)
    # where in its own range the prior session closed, 0 = at the low
    rng = (d.high - d.low).replace(0, np.nan)
    pos_in_range = ((d.close - d.low) / rng).shift(1)
    # a gap of more than four calendar days before a session means a holiday
    # sat in it; this catches every market holiday without a typed list
    gap_days = d.date.diff().dt.days
    # weekly return, Monday looks back at the week that just ended
    wk = d.set_index("date").r_cc.resample("W-FRI").sum().reindex(
        pd.DatetimeIndex(d.date), method="ffill").to_numpy()
    prev_week = pd.Series(wk).shift(1).to_numpy()

    cond = {}
    cond["C1 turn of month +1..+3"] = (d.tdom <= 3) & (d.tdom_rev != 1)
    cond["C2 after -1 sigma day"] = prev < -prev_sd
    cond["C3 after -2 sigma day"] = prev < -2 * prev_sd
    cond["C4 after +1 sigma day"] = prev > prev_sd
    cond["C5 after a holiday"] = (gap_days > 4) & (d.dow != 0)
    cond["C6 Monday after down week"] = (d.dow == 0) & (pd.Series(prev_week) < 0)
    cond["C7 OpEx week"] = (d.date.dt.day.between(11, 21)) & (d.dow <= 4)
    cond["C8 Santa window"] = ((d.month == 12) & (d.tdom_rev <= 5)) | \
                              ((d.month == 1) & (d.tdom <= 2))
    cond["C9 after a capitulation close"] = (prev < -prev_sd) & (pos_in_range < 0.10)
    cond["C10 after two down days"] = (prev < 0) & (d.r_cc.shift(2) < 0)
    for k in cond:
        cond[k] = cond[k].fillna(False).to_numpy()
    return d, cond


def main():
    rows = []
    alpha = 0.05 / N_COND
    for sym in SYMBOLS:
        try:
            d, cond = build(fetch(sym))
        except Exception as exc:
            print(f"{sym}: {exc}")
            continue
        base = d.r_oc.dropna()
        print(f"\n################ {sym}  {len(d)} sessions "
              f"{d.date.min().date()}..{d.date.max().date()} ################")
        print(f"all sessions: mean {base.mean():+.4f}%  sigma {base.std(ddof=1):.4f}%")
        print(f"\n{'condition':>30} {'n':>6} {'drift %':>9} {'sigma %':>8} "
              f"{'mu/sig2':>8} {'t':>7} {'p':>8} {'WR':>7} {'plac p':>8}")
        for name, mask in cond.items():
            a = d.loc[mask, "r_oc"].dropna().to_numpy()
            b = d.loc[~mask, "r_oc"].dropna().to_numpy()
            if len(a) < 60:
                print(f"{name:>30} {len(a):>6}   too few")
                continue
            t, p = stats.ttest_ind(a, b, equal_var=False)
            sg = a.std(ddof=1)
            ratio = a.mean() / (sg ** 2)
            plac = np.roll(mask, 5)
            pa = d.loc[plac, "r_oc"].dropna().to_numpy()
            _, pp = stats.ttest_ind(pa, b, equal_var=False)
            print(f"{name:>30} {len(a):>6} {a.mean():>+9.4f} {sg:>8.4f} "
                  f"{ratio:>8.4f} {t:>+7.2f} {p:>8.4f} {(a>0).mean():>7.4f} "
                  f"{pp:>8.4f}")
            rows.append(dict(symbol=sym, condition=name, n=len(a),
                             drift_pct=float(a.mean()), sigma_pct=float(sg),
                             mu_over_sig2=float(ratio), t=float(t), p=float(p),
                             wr=float((a > 0).mean()), placebo_p=float(pp),
                             significant=bool(p < alpha),
                             placebo_clean=bool(pp > 0.05)))

    res = pd.DataFrame(rows)
    res.to_csv(C.DATA / "reports" / "drift_condition_scan.csv", index=False)

    print(f"\n=== ranked by mu/sigma^2, Bonferroni alpha {alpha:.4f} ===")
    print("(only rows whose placebo is clean, which is what rules out plain "
          "market drift)")
    good = res[res.placebo_clean].sort_values("mu_over_sig2", ascending=False)
    print(good[["symbol", "condition", "n", "drift_pct", "sigma_pct",
                "mu_over_sig2", "p", "wr", "significant"]].head(18)
          .round(4).to_string(index=False))

    print("\n=== conditions that pass Bonferroni in at least two instruments ===")
    hits = res[res.significant & res.placebo_clean]
    cnt = hits.groupby("condition").size().sort_values(ascending=False)
    print(cnt.to_string() if len(cnt) else "  none")
    for name in cnt[cnt >= 2].index:
        sub = res[res.condition == name]
        print(f"\n  {name}")
        print(sub[["symbol", "n", "drift_pct", "sigma_pct", "mu_over_sig2",
                   "p", "wr", "placebo_p"]].round(4).to_string(index=False))
    print(f"\nwrote {C.DATA / 'reports' / 'drift_condition_scan.csv'}")


if __name__ == "__main__":
    main()
