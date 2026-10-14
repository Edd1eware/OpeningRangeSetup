"""Calendar effects: the last daily-frequency family, and the cheapest to test.

Why this family
---------------
Every negative in this project is intraday. The daily family stayed open for
lack of sample, not for lack of a result. Calendar effects are the part of it
that needs no extra data at all beyond the dates already on disk, and two of
them were documented and replicated long before this project existed:

    TURN OF THE MONTH   equity index returns concentrate in the last trading
                        day of a month and the first few of the next. One of
                        the most replicated calendar anomalies there is.
    DAY OF THE WEEK     the classic Monday effect, which has largely decayed in
                        index futures, so this one is close to a negative
                        control: finding it strong would be a warning sign
                        about the measurement, not a discovery.

And two that are mechanical features of the market's own plumbing rather than
behavioural claims:

    OPEX                the third Friday, when index options expire and dealer
                        hedging unwinds.
    QUARTER END         index rebalancing and window dressing.

Every date here is derived from the calendar exactly -- third Friday, last
trading day, quarter boundary -- so nothing depends on a hand-typed list that
could be silently wrong. Macro release days (FOMC, CPI, NFP) are deliberately
NOT included: they need a verified schedule, and a mistyped date would corrupt
the test without announcing itself.

Pre-registration
----------------
PRIMARY (published, alpha 0.05/2, sign must match):
    H7  turn of month, days {-1,+1,+2,+3} around the boundary -> POSITIVE
    H8  day of week: Monday weaker than the rest -> NEGATIVE for Monday

EXPLORATORY (alpha 0.05/3):
    H9   OpEx day (third Friday)
    H10  quarter-end day
    H11  first trading day of the month on its own

Reported as the open-to-close return in ticks, year by year, and then as a
trade with the 300-tick bracket that script 37 found optimal, so the answer is
in the units the objective uses rather than in abstract returns.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as C
from progress import track


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DS = _load("ds26", "26_rth_ml_dataset.py")
PATHS: dict = {}       # session -> dense 1s arrays, filled by load_paths()


def load_paths() -> None:
    """One dense 1-second RTH path per session, keyed by date.

    Needed because a calendar effect has to be judged by what a bracket would
    actually have done, and that depends on the ORDER the barriers were
    touched, which only the path knows.
    """
    bars = DS.load_bars()
    for sess, g in track(list(bars.groupby("session", sort=True)),
                         label="session paths"):
        s = DS.session_grid(g)
        if s:
            PATHS[pd.Timestamp(sess)] = s

TICK = 0.25
COST_TICKS = 1.8
BRACKET = 300
N_BOOT = 10000
SEED = 20261013


def load_daily() -> pd.DataFrame:
    """Open-to-close in ticks per session, plus the path extremes for brackets."""
    import duckdb
    con = duckdb.connect()
    con.execute("SET TimeZone='America/New_York'")
    src = (C.DATA / "bars").as_posix() + "/bars_1s_*.parquet"
    df = con.sql(f"""
        with rth as (
            select session, ts_ny, open, high, low, close
            from read_parquet('{src}')
            where strftime(ts_ny,'%H:%M:%S') between '09:30:00' and '16:00:00'
        )
        select session,
               min(ts_ny)                                      as t0,
               arg_min(open, ts_ny)                            as px_open,
               arg_max(close, ts_ny)                           as px_close,
               max(high)                                       as px_high,
               min(low)                                        as px_low
        from rth group by session order by session
    """).df()
    con.close()
    d = pd.DataFrame({
        "session": pd.to_datetime(df.session),
        "px_open": df.px_open.astype(float),
        "px_close": df.px_close.astype(float),
        "px_high": df.px_high.astype(float),
        "px_low": df.px_low.astype(float),
    })
    d["r_day"] = (d.px_close - d.px_open) / TICK
    d["year"] = d.session.dt.year
    d["month"] = d.session.dt.month
    d["dow"] = d.session.dt.dayofweek
    d = d.sort_values("session").reset_index(drop=True)

    # rank inside the month, forward and backward, over TRADING days present
    g = d.groupby([d.year, d.month])
    d["tdom"] = g.cumcount() + 1                       # 1 = first trading day
    d["tdom_rev"] = g.cumcount(ascending=False) + 1    # 1 = last trading day
    d["is_last"] = d.tdom_rev == 1
    d["is_first"] = d.tdom == 1
    # turn of month: last trading day of the previous month, plus the first
    # three of this one
    d["tom"] = d.is_last.shift(1, fill_value=False) | d.tdom.le(3)
    d.loc[d.is_last, "tom"] = True
    d["opex"] = (d.dow == 4) & d.session.dt.day.between(15, 21)
    d["qend"] = d.is_last & d.month.isin([3, 6, 9, 12])
    return d


def bracket_trade(d: pd.DataFrame, side: int, k: int = BRACKET) -> np.ndarray:
    """R of a k-tick symmetric bracket from the open, resolved on the 1s PATH.

    The first version of this read only the day's high and low. That is wrong
    here and badly so: NQ's daily range runs well over a thousand ticks, so a
    300-tick barrier pair sits INSIDE the range on nearly every session, and
    the conservative tie rule then charged the stop almost every day. It
    produced a win rate of 0.375 on days whose mean return was +428 ticks,
    which is not a finding, it is the measurement eating itself.

    Resolving on the second-by-second path is the only honest way: whichever
    barrier is touched first, wins. The tie rule still applies, but now only
    inside a single SECOND, where it is genuinely undecidable, and the audit in
    script 36 measured that case at well under one percent.
    """
    paths = PATHS
    kk = k * TICK
    out = np.full(len(d), np.nan)
    for i, (sess, entry) in enumerate(zip(d.session.to_numpy(),
                                          d.px_open.to_numpy())):
        p = paths.get(pd.Timestamp(sess))
        if p is None:
            continue
        hi, lo, cl = p["high"], p["low"], p["close"]
        if side > 0:
            m_tp = hi >= entry + kk; m_sl = lo <= entry - kk
        else:
            m_tp = lo <= entry - kk; m_sl = hi >= entry + kk
        INF = 1 << 30
        i_tp = int(np.argmax(m_tp)) if m_tp.any() else INF
        i_sl = int(np.argmax(m_sl)) if m_sl.any() else INF
        if i_tp == INF and i_sl == INF:
            out[i] = side * (cl[-1] - entry) / kk
        elif i_sl <= i_tp:
            out[i] = -1.0
        else:
            out[i] = 1.0
    return out


def report(d, mask, label, rng, rows):
    """Open-to-close in ticks and a 300-tick bracket, inside vs outside."""
    a = d.loc[mask]; b = d.loc[~mask]
    if len(a) < 20:
        return
    ra = a.r_day.to_numpy(); rb = b.r_day.to_numpy()
    from scipy import stats
    t, p = stats.ttest_ind(ra, rb, equal_var=False)
    boot = np.array([rng.choice(ra, len(ra), replace=True).mean()
                     for _ in range(2000)])
    # the bracket version: long on the flagged days
    R = bracket_trade(a, +1)
    net = R * BRACKET - COST_TICKS
    rows.append(dict(effect=label, n_in=len(a), n_out=len(b),
                     mean_in_ticks=float(ra.mean()), mean_out_ticks=float(rb.mean()),
                     t=float(t), p=float(p),
                     lo95=float(np.percentile(boot, 2.5)),
                     hi95=float(np.percentile(boot, 97.5)),
                     bracket_wr=float((R > 0).mean()),
                     bracket_net_ticks=float(net.mean())))
    print(f"  {label:26} n {len(a):5} mean_in {ra.mean():+9.2f} tk  "
          f"mean_out {rb.mean():+9.2f}  t {t:+.2f}  p {p:.4f}  "
          f"CI_in [{np.percentile(boot,2.5):+.1f},{np.percentile(boot,97.5):+.1f}]  "
          f"bracket300 WR {(R>0).mean():.3f} net {net.mean():+.2f} tk")


def main():
    d = load_daily()
    load_paths()
    rng = np.random.default_rng(SEED)
    print(f"{len(d)} sessions, {d.session.min().date()} .. {d.session.max().date()}")
    print(d.groupby("year").size().to_string())
    if len(d) < 300:
        print("\nWARNING: fewer than 300 sessions; the 2021-2025 bars are not "
              "built yet. Run 03_build_bars.py after the download finishes.")
    print()

    rows = []
    print("=== PRIMARY (alpha 0.05/2 = 0.025) ===")
    report(d, d.tom, "H7 turn of month", rng, rows)
    report(d, d.dow == 0, "H8 Monday", rng, rows)
    print("\n=== EXPLORATORY (alpha 0.05/3 = 0.0167) ===")
    report(d, d.opex, "H9 OpEx third Friday", rng, rows)
    report(d, d.qend, "H10 quarter end", rng, rows)
    report(d, d.is_first, "H11 first trading day", rng, rows)

    out = pd.DataFrame(rows)
    out["sig_primary"] = out.p < 0.025
    out["sig_exploratory"] = out.p < 0.05 / 3
    out.to_csv(C.DATA / "reports" / "calendar_effects.csv", index=False)

    print("\n=== year x metric for the strongest primary effect ===")
    best = out.iloc[out.p.idxmin()]
    mask = {"H7 turn of month": d.tom, "H8 Monday": d.dow == 0,
            "H9 OpEx third Friday": d.opex, "H10 quarter end": d.qend,
            "H11 first trading day": d.is_first}[best.effect]
    sub = d.loc[mask].copy()
    sub["R"] = bracket_trade(sub, +1)
    yr = sub.groupby("year").agg(
        trades=("R", "size"), wr=("R", lambda x: (x > 0).mean()),
        ev_gross_ticks=("R", lambda x: x.mean() * BRACKET))
    yr["ev_net_ticks"] = yr.ev_gross_ticks - COST_TICKS
    yr["trades_per_month"] = yr.trades / 12
    tot = pd.DataFrame([dict(trades=len(sub), wr=float((sub.R > 0).mean()),
                             ev_gross_ticks=float(sub.R.mean() * BRACKET),
                             ev_net_ticks=float(sub.R.mean() * BRACKET - COST_TICKS),
                             trades_per_month=np.nan)], index=["TOTAL"])
    print(f"effect: {best.effect}, long with a {BRACKET}-tick bracket from the open")
    print(pd.concat([yr, tot]).round(4).to_string())
    print(f"\nbreakeven WR at RR 1:1 with {COST_TICKS} tk cost = "
          f"{(BRACKET + COST_TICKS) / (2 * BRACKET):.4f}")
    print(f"wrote {C.DATA / 'reports' / 'calendar_effects.csv'}")


if __name__ == "__main__":
    main()
