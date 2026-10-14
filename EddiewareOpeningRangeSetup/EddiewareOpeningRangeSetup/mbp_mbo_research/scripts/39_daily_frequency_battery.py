"""Daily-frequency hypotheses, run at last with enough sessions to decide.

Why these and why now
---------------------
Every negative this project has produced is an INTRADAY negative: 1-second
price and volume, order flow, brackets from 20 to 400 ticks. One family was
never properly tested, and not because it failed: because 150 sessions could
not decide it. Script 33 ran the published intraday-momentum test and came back
with a 95% interval of plus or minus 44 ticks, which cannot tell a real small
effect from zero. That is a power failure, not a result, and calling it a
refutation would be the mirror of the error that killed the K=150 "edge".

With the 2021-2025 download the sample goes from 150 to about 976 sessions, so
these become answerable. They are also the right SHAPE for the objective:
one trade per day, exit by the clock, which is exactly the policy that script
37 found maximises the 50K pass probability.

Pre-registration
----------------
PRIMARY, two tests, specified by other people on other data before this project
existed, so they carry an alpha of 0.05/2 and the sign must match to count:

    H1  r(09:30-10:00)  ->  r(15:30-16:00)      positive       Gao et al. 2018
    H2  r(15:00-15:30)  ->  r(15:30-16:00)      positive       Gao et al. 2018

EXPLORATORY, four tests invented here, alpha 0.05/4, reported whatever they do:

    H3  overnight gap (prev close -> today open) -> r(09:30-10:00)
    H4  r(09:30-10:00) -> r(10:00-16:00)         the opening drive
    H5  day of week    -> r(09:30-16:00)
    H6  |r| yesterday  -> |r| today              volatility clustering, which is
                                                 about SIZING, not direction

Everything is reported year by year as well as pooled, because a pooled total
hides whether an effect is consistent or carried by one fat year, and years are
the natural out-of-sample blocks here. Trading translations carry the 1.8 tick
cost and a session bootstrap.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

TICK = 0.25
COST_TICKS = 1.8
N_BOOT = 10000
SEED = 20261013
EDGES = ["09:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30",
         "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00"]


def load_halfhours() -> pd.DataFrame:
    """One row per session: every half-hour return in ticks, plus the gap."""
    import duckdb
    con = duckdb.connect()
    con.execute("SET TimeZone='America/New_York'")
    src = (C.DATA / "bars").as_posix() + "/bars_1s_*.parquet"
    df = con.sql(f"""
        select session,
               strftime(ts_ny,'%H:%M:%S') as et,
               close
        from read_parquet('{src}')
        where strftime(ts_ny,'%H:%M:%S') between '09:29:00' and '16:00:59'
        order by session, ts_ny
    """).df()
    con.close()

    rows = []
    for sess, g in df.groupby("session", sort=True):
        et = g.et.to_numpy(); close = g.close.to_numpy()
        px, ok = {}, True
        for e in EDGES:
            m = et <= e + ":00"
            if not m.any():
                ok = False
                break
            px[e] = float(close[m][-1])
        if not ok:
            continue
        r = {"session": pd.Timestamp(sess), "open_0930": px["09:30"],
             "close_1600": px["16:00"]}
        for i in range(len(EDGES) - 1):
            r[f"r{i+1}"] = (px[EDGES[i + 1]] - px[EDGES[i]]) / TICK
        rows.append(r)
    hh = pd.DataFrame(rows).sort_values("session").reset_index(drop=True)
    hh["year"] = hh.session.dt.year
    hh["dow"] = hh.session.dt.dayofweek
    hh["r_day"] = (hh.close_1600 - hh.open_0930) / TICK
    hh["r_rest"] = hh[[f"r{i}" for i in range(2, 14)]].sum(axis=1)
    # the gap crosses a contract roll a handful of times a year and the series
    # jumps by the calendar spread there, so the extreme tail is clipped out
    # rather than allowed to dominate a regression
    prev_close = hh.close_1600.shift(1)
    gap = (hh.open_0930 - prev_close) / TICK
    lim = gap.abs().quantile(0.99)
    hh["gap"] = gap.where(gap.abs() <= lim)
    hh["abs_prev"] = hh.r_day.abs().shift(1)
    return hh


def nw_t(x, y, lags: int = 5):
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    X = np.column_stack([np.ones_like(x), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    S = (X * resid[:, None]).T @ (X * resid[:, None])
    for L in range(1, lags + 1):
        w = 1.0 - L / (lags + 1)
        A = (X[L:] * resid[L:, None]).T @ (X[:-L] * resid[:-L, None])
        S += w * (A + A.T)
    inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(inv @ S @ inv))
    from scipy import stats
    t = beta[1] / se[1]
    return float(beta[1]), float(t), float(2 * (1 - stats.t.cdf(abs(t), n - k))), int(n)


def trade_table(hh, pred_col, fwd_col, label, rng):
    """Sign of the predictor, held through the forward window, cost charged.

    Reported year by year because a pooled total cannot show whether an effect
    is consistent or carried by one year.
    """
    rows = []
    for year, g in list(hh.groupby("year")) + [("TOTAL", hh)]:
        pred = g[pred_col].to_numpy(dtype=float)
        fwd = g[fwd_col].to_numpy(dtype=float)
        m = ~(np.isnan(pred) | np.isnan(fwd)) & (np.sign(pred) != 0)
        r = np.sign(pred[m]) * fwd[m]
        if len(r) < 20:
            continue
        net = r - COST_TICKS
        wins = net[net > 0].sum(); loss = -net[net < 0].sum()
        boot = np.array([rng.choice(net, len(net), replace=True).mean()
                         for _ in range(2000)])
        rows.append(dict(rule=label, year=year, n=len(r),
                         trades_per_month=len(r) / 12 if year != "TOTAL" else np.nan,
                         wr=float((r > 0).mean()),
                         ev_gross_ticks=float(r.mean()),
                         ev_net_ticks=float(net.mean()),
                         pf=float(wins / loss) if loss > 0 else np.inf,
                         lo95=float(np.percentile(boot, 2.5)),
                         hi95=float(np.percentile(boot, 97.5))))
    return rows


def main():
    hh = load_halfhours()
    rng = np.random.default_rng(SEED)
    print(f"{len(hh)} sessions, {hh.session.min().date()} .. {hh.session.max().date()}")
    print(hh.groupby("year").size().to_string(), "\n")
    if len(hh) < 300:
        print("WARNING: fewer than 300 sessions. The 2021-2025 download has not "
              "been built into bars yet; run 03_build_bars.py first.\n")

    tests = [
        ("H1 first->last", "r1", "r13", "primary", +1),
        ("H2 penult->last", "r12", "r13", "primary", +1),
        ("H3 gap->first30", "gap", "r1", "exploratory", 0),
        ("H4 first30->rest", "r1", "r_rest", "exploratory", 0),
        ("H6 |r| persistence", "abs_prev", "r_day", "exploratory", 0),
    ]
    alpha = {"primary": 0.05 / 2, "exploratory": 0.05 / 4}

    print("=== regressions, Newey-West t ===")
    out = []
    for name, xc, yc, kind, want in tests:
        x = hh[xc].to_numpy(dtype=float)
        y = hh[yc].to_numpy(dtype=float)
        if name.startswith("H6"):
            y = np.abs(y)
        b, t, p, n = nw_t(x, y)
        sig = p < alpha[kind] and (want == 0 or np.sign(b) == want)
        print(f"  {name:22} {kind:12} n {n:5} beta {b:+.4f}  t {t:+.2f}  "
              f"p {p:.4f}  alpha {alpha[kind]:.4f}  -> {'SIGNIFICANT' if sig else 'no'}")
        out.append(dict(test=name, kind=kind, n=n, beta=b, t=t, p=p,
                        alpha=alpha[kind], significant=bool(sig)))

    # H5 needs a different shape: a group comparison, not a slope
    print("\n=== H5 day of week -> open-to-close, ticks ===")
    dow = hh.groupby("dow").r_day.agg(["count", "mean", "std"])
    dow["t"] = dow["mean"] / (dow["std"] / np.sqrt(dow["count"]))
    dow.index = ["Mon", "Tue", "Wed", "Thu", "Fri"][:len(dow)]
    print(dow.round(3).to_string())

    print("\n=== trading translation, year x metric ===")
    rows = []
    for name, xc, yc, kind, _ in tests:
        if name.startswith("H6"):
            continue
        rows += trade_table(hh, xc, yc, name, rng)
    td = pd.DataFrame(rows)
    for rule, g in td.groupby("rule"):
        print(f"\n--- {rule} (breakeven WR at RR 1:1 with cost = depends on the "
              f"size of the move; EV net is the number that decides) ---")
        print(g[["year", "n", "wr", "ev_gross_ticks", "ev_net_ticks", "pf",
                 "lo95", "hi95"]].round(3).to_string(index=False))

    pd.DataFrame(out).to_csv(C.DATA / "reports" / "daily_battery_tests.csv", index=False)
    td.to_csv(C.DATA / "reports" / "daily_battery_trades.csv", index=False)
    dow.to_csv(C.DATA / "reports" / "daily_battery_dow.csv")
    hh.to_parquet(C.DATA / "features" / "halfhour_returns_all.parquet", index=False)
    print(f"\nwrote daily_battery_*.csv to {C.DATA / 'reports'}")


if __name__ == "__main__":
    main()
