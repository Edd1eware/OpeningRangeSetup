"""Condition the turn-of-month drift on volatility, because sigma is the half
of the ratio that can actually be forecast.

The geometry of note 08 says a bracket's edge is governed by

    2P - 1  ~=  mu * b / sigma^2

Every condition tried so far has gone after mu. That is the hard half: mu needs
decades to estimate and the scan in script 48 showed only one condition that
replicates. Sigma is the other half, it enters SQUARED, and -- this is the whole
point -- volatility clusters. Last month's realised volatility forecasts this
month's; last decade's mean return does not forecast this decade's. So a filter
on forecast volatility is far better powered than any filter on forecast drift.

Halving sigma is worth four times as much as doubling mu.

The null that matters is NOT "does mu differ across volatility buckets". It is
the reverse: the filter wins as long as mu does NOT shrink in proportion to
sigma^2. So the test is deliberately set up to be falsified by a proportional
mu, and the comparison is reported as the ratio, not as a p-value on mu.

Two sizing regimes are reported because they reward volatility differently:

    FIXED STOP      notional and dollar risk fixed, so the stop in percent b is
                    fixed. Value ~ mu/sigma^2. Low volatility wins hard, but
                    the barrier is reached less often and more days mark to
                    market at the bell.
    SCALED STOP     the stop is set to c*sigma, which holds the resolution rate
                    roughly constant across regimes. Then mu*b/sigma^2 = c*mu/sigma,
                    so value ~ mu/sigma. Low volatility wins less, and the win
                    is not an artefact of unresolved days.

The volatility forecast is causal: realised close-to-close volatility over the
previous 20 sessions, ranked against its own trailing 500-session distribution,
both shifted by one day. Nothing in the bucket assignment can see the session
being traded, and the percentile is trailing so it does not borrow the whole
sample's volatility distribution.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as C


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SC = _load("sc48", "48_drift_condition_scan.py")
SYMBOLS = ("^GSPC", "^NDX", "NQ=F")

RISK_USD = 1500.0
MNQ_PER_POINT = 2.0
MNQ_COMM = 1.0
TICK = 0.25
N_MNQ = 5                       # the planning configuration from note 08
BUCKETS = ("low", "mid", "high")


def p_up_first(mu, sigma, b):
    """Brownian first passage to symmetric barriers at +/- b."""
    return 1.0 / (1.0 + np.exp(-2.0 * mu * b / sigma ** 2))


def add_vol_forecast(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    # causal: both the 20-day realised vol and its trailing rank are shifted
    rv = d.r_cc.rolling(20, min_periods=15).std().shift(1)
    d["rv20"] = rv
    d["rv_pct"] = rv.rolling(500, min_periods=250).rank(pct=True)
    d["up_reach"] = (d.high / d.open - 1.0) * 100
    d["dn_reach"] = (1.0 - d.low / d.open) * 100
    return d


def bucket_of(d: pd.DataFrame) -> pd.Series:
    p = d.rv_pct
    out = pd.Series(index=d.index, dtype=object)
    out[p <= 1 / 3] = "low"
    out[(p > 1 / 3) & (p <= 2 / 3)] = "mid"
    out[p > 2 / 3] = "high"
    return out


def main():
    rows = []
    for sym in SYMBOLS:
        try:
            d, cond = SC.build(SC.fetch(sym))
        except Exception as exc:
            print(f"{sym}: {exc}")
            continue
        d = add_vol_forecast(d)
        tom = pd.Series(cond["C1 turn of month +1..+3"], index=d.index)
        buck = bucket_of(d)
        ok = d.rv_pct.notna() & d.r_oc.notna()

        print(f"\n################ {sym}  {len(d)} sessions "
              f"{d.date.min().date()}..{d.date.max().date()} ################")

        # does the forecast work at all? cheapest possible validation
        print("  --- is the volatility forecast actually predictive? ---")
        print(f"  {'bucket':>7} {'n':>6} {'fcst rv20 %':>12} {'realised sigma(r_oc) %':>24}")
        for b in BUCKETS:
            g = d[ok & (buck == b)]
            print(f"  {b:>7} {len(g):>6} {g.rv20.median():>12.4f} "
                  f"{g.r_oc.std(ddof=1):>24.4f}")

        print("  --- turn-of-month days split by forecast volatility ---")
        print(f"  {'bucket':>7} {'n':>5} {'mu %':>9} {'sigma %':>8} "
              f"{'mu/sigma':>9} {'mu/sigma2':>10} {'t vs 0':>7} {'p':>7} "
              f"{'WR day':>7} {'ctrl mu %':>10}")
        per_sym = {}
        for b in BUCKETS:
            m = ok & tom & (buck == b)
            a = d.loc[m, "r_oc"].to_numpy()
            if len(a) < 50:
                print(f"  {b:>7} {len(a):>5}  too few")
                continue
            mu, sg = float(a.mean()), float(a.std(ddof=1))
            se = sg / np.sqrt(len(a))
            t = mu / se
            p = 2 * stats.t.sf(abs(t), len(a) - 1)
            # control = non-window days in the SAME volatility bucket, so the
            # comparison is not contaminated by the regime itself
            cm = ok & ~tom & (buck == b)
            c = d.loc[cm, "r_oc"].to_numpy()
            print(f"  {b:>7} {len(a):>5} {mu:>+9.4f} {sg:>8.4f} {mu/sg:>9.4f} "
                  f"{mu/sg**2:>10.4f} {t:>+7.2f} {p:>7.4f} "
                  f"{(a>0).mean():>7.4f} {c.mean():>+10.4f}")
            per_sym[b] = dict(mu=mu, sigma=sg, n=len(a), arr=a,
                              ctrl_mu=float(c.mean()), ctrl_sigma=float(c.std(ddof=1)),
                              reach_up=d.loc[m, "up_reach"].to_numpy(),
                              reach_dn=d.loc[m, "dn_reach"].to_numpy(),
                              price=float(d.close.iloc[-1]))
            rows.append(dict(symbol=sym, bucket=b, n=len(a), mu_pct=mu,
                             sigma_pct=sg, mu_over_sigma=mu / sg,
                             mu_over_sigma2=mu / sg ** 2, t=t, p=p,
                             wr_day=float((a > 0).mean()),
                             ctrl_mu_pct=float(c.mean())))

        # the falsification: is mu proportional to sigma^2?
        if "low" in per_sym and "high" in per_sym:
            lo, hi = per_sym["low"], per_sym["high"]
            prop = hi["mu"] * (lo["sigma"] / hi["sigma"]) ** 2
            print("  --- the falsification test ---")
            print(f"    if mu were proportional to sigma^2, the low bucket "
                  f"should show {prop:+.4f}%")
            print(f"    it shows {lo['mu']:+.4f}%  -> "
                  f"{'FILTER WINS' if lo['mu'] > prop else 'proportional, filter is worthless'}")
            tt, pp = stats.ttest_ind(lo["arr"], hi["arr"], equal_var=False)
            print(f"    mu(low) vs mu(high): t {tt:+.2f}  p {pp:.4f}  "
                  f"(a null result HELPS the filter)")
            print(f"    ratio gain, fixed stop:  "
                  f"{(lo['mu']/lo['sigma']**2)/(hi['mu']/hi['sigma']**2):.2f}x")
            print(f"    ratio gain, scaled stop: "
                  f"{(lo['mu']/lo['sigma'])/(hi['mu']/hi['sigma']):.2f}x")

        # what it means for the actual 50K bracket, NQ only
        if sym == "NQ=F" and per_sym:
            price = per_sym[list(per_sym)[0]]["price"]
            notional = N_MNQ * MNQ_PER_POINT * price
            b_fixed = RISK_USD / notional * 100
            cost = (MNQ_COMM + TICK * MNQ_PER_POINT) * N_MNQ
            be = 0.5 + cost / (2 * RISK_USD)
            print(f"\n  --- the 50K bracket: {N_MNQ} MNQ, ${RISK_USD:,.0f} risk, "
                  f"stop {b_fixed:.3f}% = {b_fixed/100*price:.0f} pts, "
                  f"breakeven {be:.4f} ---")
            print(f"  {'bucket':>7} {'regime':>7} {'stop %':>7} {'stop pts':>9} "
                  f"{'resolve':>8} {'WR':>7} {'EV$':>9} {'edge$ vs ctrl':>14}")
            for bk in BUCKETS:
                if bk not in per_sym:
                    continue
                s = per_sym[bk]
                for regime, bb in (("fixed", b_fixed),
                                   ("scaled", b_fixed * s["sigma"] / per_sym["mid"]["sigma"]
                                    if "mid" in per_sym else b_fixed)):
                    reach = float(((s["reach_up"] >= bb) | (s["reach_dn"] >= bb)).mean())
                    # a scaled stop keeps dollar risk fixed by changing size
                    size_notional = RISK_USD / (bb / 100)
                    pw = p_up_first(s["mu"], s["sigma"], bb)
                    pc = p_up_first(s["ctrl_mu"], s["ctrl_sigma"], bb)
                    n_eq = size_notional / (MNQ_PER_POINT * price)
                    cst = (MNQ_COMM + TICK * MNQ_PER_POINT) * n_eq
                    ev_w = ((2 * pw - 1) * RISK_USD * reach
                            + (1 - reach) * (s["mu"] / 100) * size_notional - cst)
                    ev_c = ((2 * pc - 1) * RISK_USD * reach
                            + (1 - reach) * (s["ctrl_mu"] / 100) * size_notional - cst)
                    print(f"  {bk:>7} {regime:>7} {bb:>7.3f} {bb/100*price:>9.0f} "
                          f"{reach:>8.1%} {pw:>7.4f} {ev_w:>+9.2f} {ev_w-ev_c:>+14.2f}")
                    rows.append(dict(symbol=sym, bucket=bk, regime=regime,
                                     stop_pct=bb, resolve=reach, wr_model=pw,
                                     breakeven=be, ev_usd=ev_w,
                                     edge_usd=ev_w - ev_c, n=s["n"]))

    res = pd.DataFrame(rows)
    out = C.DATA / "reports" / "vol_conditioned_drift.csv"
    res.to_csv(out, index=False)

    print("\n=== does the low-volatility filter replicate across instruments? ===")
    g = res[res.bucket.notna() & res.regime.isna()] if "regime" in res else res
    print(f"  {'symbol':>7} {'mu/sig2 low':>12} {'mu/sig2 mid':>12} "
          f"{'mu/sig2 high':>13} {'low>high?':>10}")
    for sym, gg in g.groupby("symbol"):
        v = {r.bucket: r.mu_over_sigma2 for r in gg.itertuples() if pd.notna(r.mu_over_sigma2)}
        if len(v) < 3:
            continue
        print(f"  {sym:>7} {v['low']:>12.4f} {v['mid']:>12.4f} {v['high']:>13.4f} "
              f"{str(v['low'] > v['high']):>10}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
