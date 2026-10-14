"""Market intraday momentum on NQ: does the first half hour predict the last?

Why this hypothesis and not another
-----------------------------------
Everything this project has tested was invented here, which means every result
carried the full multiple-testing burden of a search. This one was not invented
here. Gao, Han, Li and Zhou (2018), "Market intraday momentum", report that the
return of the FIRST half hour of the session predicts the return of the LAST
half hour, on the S&P 500 ETF and on index futures, out of sample, over
decades. They also report that the PENULTIMATE half hour predicts the last one.

That matters for the Bonferroni arithmetic. The two primary tests below were
specified by someone else, on other data, before this project existed, so they
are two tests, not two cells of a sweep. Anything beyond them is labelled
exploratory and corrected.

It also matters for the Lucid objective. The rule is one trade per day, held
for thirty minutes, with the exit fixed by the clock rather than by a barrier.
Script 28 found that one trade per day with a large stop is exactly the shape
that maximises the pass probability of a 50K evaluation, so if this effect is
present at all, it lands in the right part of the payoff structure.

Primary tests, fixed before running
-----------------------------------
    H1   r_last ~ r_first      (first half hour  09:30-10:00 -> 15:30-16:00)
    H2   r_last ~ r_penult     (15:00-15:30 -> 15:30-16:00)
Significance at 0.05/2 on a two-sided t with Newey-West standard errors, and
the sign must be POSITIVE (momentum, not reversal) to count as a replication.

The trading translation, also fixed
-----------------------------------
At 15:30 take the sign of the predictor, hold to 16:00, exit at the close. Cost
1.8 ticks round trip. Reported in ticks per trade, with the breakeven that the
cost implies, split in half chronologically so an in-sample optimum is never
presented as a forward expectation. With 150 sessions the halves are 75 each,
which is small, and the interval will say so.

A clean positive here is worth buying history for: this effect needs only
half-hourly closes, so 1-minute bars over a decade cost a tiny fraction of what
1-second bars over five years cost.
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

# half-hour bucket edges, ET
EDGES = ["09:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30",
         "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00"]


def load_halfhours() -> pd.DataFrame:
    """One row per session, one column per half-hour return in ticks."""
    import duckdb
    con = duckdb.connect()
    con.execute("SET TimeZone='America/New_York'")
    src = (C.DATA / "bars" / "bars_1s_2026.parquet").as_posix()
    df = con.sql(f"""
        select session,
               strftime(ts_ny,'%H:%M:%S') as et,
               close
        from '{src}'
        where strftime(ts_ny,'%H:%M:%S') between '09:29:00' and '16:00:59'
        order by session, ts_ny
    """).df()
    con.close()

    rows = []
    for sess, g in df.groupby("session", sort=True):
        et = g.et.to_numpy()
        close = g.close.to_numpy()
        # last print at or before each edge; the 09:30 edge uses the last print
        # BEFORE the open so the first bucket is a true open-to-10:00 return
        px = {}
        ok = True
        for e in EDGES:
            m = et <= (e + ":00" if len(e) == 5 else e)
            if not m.any():
                ok = False
                break
            px[e] = float(close[m][-1])
        if not ok:
            continue
        r = {"session": pd.Timestamp(sess)}
        for i in range(len(EDGES) - 1):
            a, b = EDGES[i], EDGES[i + 1]
            r[f"r{i+1}"] = (px[b] - px[a]) / TICK
        r["close_1600"] = px["16:00"]
        rows.append(r)
    return pd.DataFrame(rows)


def newey_west_t(x: np.ndarray, y: np.ndarray, lags: int = 5):
    """OLS slope of y on x with a Newey-West t, intercept included."""
    X = np.column_stack([np.ones_like(x), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    S = (X * resid[:, None]).T @ (X * resid[:, None])
    for L in range(1, lags + 1):
        w = 1.0 - L / (lags + 1)
        A = (X[L:] * resid[L:, None]).T @ (X[:-L] * resid[:-L, None])
        S += w * (A + A.T)
    XtX_inv = np.linalg.inv(X.T @ X)
    V = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.diag(V))
    from scipy import stats
    t = beta[1] / se[1]
    p = 2 * (1 - stats.t.cdf(abs(t), n - k))
    return float(beta[1]), float(t), float(p)


def trade_stats(pred: np.ndarray, fwd: np.ndarray, label: str):
    """Sign of pred, held through fwd, cost charged. Reported in ticks."""
    pos = np.sign(pred)
    taken = pos != 0
    r = pos[taken] * fwd[taken]
    net = r - COST_TICKS
    wins = net[net > 0].sum()
    loss = -net[net < 0].sum()
    rng = np.random.default_rng(SEED)
    boot = np.array([rng.choice(net, len(net), replace=True).mean()
                     for _ in range(N_BOOT)])
    return dict(scope=label, n=int(taken.sum()),
                wr=float((r > 0).mean()),
                ev_gross_ticks=float(r.mean()),
                ev_net_ticks=float(net.mean()),
                pf=float(wins / loss) if loss > 0 else np.inf,
                lo95=float(np.percentile(boot, 2.5)),
                hi95=float(np.percentile(boot, 97.5)))


def main():
    hh = load_halfhours()
    print(f"{len(hh)} sessions with a complete half-hour grid "
          f"({hh.session.min().date()} .. {hh.session.max().date()})\n")

    r_first = hh.r1.to_numpy()
    r_penult = hh.r12.to_numpy()
    r_last = hh.r13.to_numpy()

    print("=== primary tests (Gao-Han-Li-Zhou 2018), alpha = 0.05/2 = 0.025 ===")
    out = []
    for name, x in (("H1 first->last", r_first), ("H2 penult->last", r_penult)):
        b, t, p = newey_west_t(x, r_last)
        verdict = "REPLICATES" if (p < 0.025 and b > 0) else "no"
        print(f"  {name:18} beta {b:+.4f}  t {t:+.2f}  p {p:.4f}  -> {verdict}")
        out.append(dict(test=name, beta=b, t=t, p=p, verdict=verdict))

    print("\n=== trading translation: sign(predictor) at 15:30, exit 16:00 ===")
    rows = []
    n = len(hh)
    half = n // 2
    for pname, pred in (("first", r_first), ("penult", r_penult)):
        for scope, sl in (("all", slice(None)),
                          ("first_half", slice(0, half)),
                          ("second_half", slice(half, None))):
            s = trade_stats(pred[sl], r_last[sl], f"{pname}|{scope}")
            rows.append(s)
            print(f"  {s['scope']:20} n {s['n']:4d}  WR {s['wr']:.4f}  "
                  f"gross {s['ev_gross_ticks']:+7.2f} tk  net {s['ev_net_ticks']:+7.2f} tk  "
                  f"PF {s['pf']:.3f}  CI [{s['lo95']:+.2f}, {s['hi95']:+.2f}]")

    print("\n=== exploratory: every bucket as predictor of the last "
          f"(Bonferroni alpha = {0.05/12:.5f}) ===")
    expl = []
    for i in range(1, 13):
        x = hh[f"r{i}"].to_numpy()
        b, t, p = newey_west_t(x, r_last)
        expl.append(dict(predictor=f"r{i}", beta=b, t=t, p=p,
                         sig=bool(p < 0.05 / 12)))
    ed = pd.DataFrame(expl)
    print(ed.round(4).to_string(index=False))
    print(f"  significant after correction: {int(ed.sig.sum())} of 12")

    pd.DataFrame(out).to_csv(C.DATA / "reports" / "intraday_momentum_tests.csv",
                             index=False)
    pd.DataFrame(rows).to_csv(C.DATA / "reports" / "intraday_momentum_trades.csv",
                              index=False)
    ed.to_csv(C.DATA / "reports" / "intraday_momentum_exploratory.csv", index=False)
    hh.to_parquet(C.DATA / "features" / "halfhour_returns.parquet", index=False)
    print(f"\nwrote reports to {C.DATA / 'reports'}")


if __name__ == "__main__":
    main()
