"""Same dollar risk, smaller notional, wider barrier: the micro-contract result.

Where this comes from
---------------------
Script 46 established that for a daily drift mu and volatility sigma, a
symmetric barrier at plus and minus b (in return terms) gives

    2P - 1  ~  mu * b / sigma^2

so the edge measured in DOLLARS on a trade risking R dollars is

    EV  =  (2P - 1) * R  ~  mu * b * R / sigma^2

and since R = b * N where N is the position's notional, substituting b = R/N:

    EV  ~  mu * R^2 / (N * sigma^2)

For a FIXED dollar risk the edge is inversely proportional to the notional.
Half the notional, twice the edge. This is not leverage and it does not raise
risk: the stop is the same number of dollars either way. What changes is that
a smaller position lets the same dollar stop sit FURTHER away in percentage
terms, and distance is what turns a drift into a first-passage advantage.

On a 50K evaluation the dollar stop is pinned near $1,500 by the drawdown
rules (script 37), so the only lever left is the notional, and a micro
contract is one fifth of a full one.

    1 NQ   notional ~ $500,000 at 25,000   ->  $1,500 stop sits 0.30% away
    5 MNQ  notional ~ $250,000             ->  $1,500 stop sits 0.60% away
    2 MNQ  notional ~ $100,000             ->  $1,500 stop sits 1.50% away

What stops this from being free money
-------------------------------------
THE SESSION BOUNDARY, which turns out to be the binding constraint. Lucid
requires every position flat by 16:45 ET and allows no overnight or weekend
hold on an evaluation account. A barrier that needs more than one session
therefore does not exist as a trade: it gets closed at market at the bell,
keeping none of the first-passage advantage and only whatever the drift
happened to deliver. The widest configurations are ruled out by that alone --
a 375-point stop resolves inside a session only 29% of the time -- so the
payoff below is MEASURED on same-session paths with a forced close, never
modelled with a multi-day resolution rate.

Two smaller frictions, both charged: commission is per contract, so five
micros pay five micro commissions; and the position must be a whole number of
contracts, so not every notional is reachable.

Two columns are reported for window days. The MODEL column carries 26 years of
drift estimate behind it and is the one to plan with. The MEASURED column has
about 70 sessions behind it and is shown only as a consistency check -- it is
far too small to decide anything, and today's notes already contain one
expensive lesson about believing a number built on that few days.
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

TICK = 0.25
NQ_PER_POINT = 20.0
MNQ_PER_POINT = 2.0
RISK_USD = 1500.0
DRIFT_PCT = 0.1088            # NQ=F window-day open-to-close drift, 26 years
CONTROL_DRIFT_PCT = 0.0296    # non-window days, same source
PRICE = 25000.0
NQ_COMM = 4.0
MNQ_COMM = 1.0


def p_up_first(mu, sigma, b):
    return 1.0 / (1.0 + np.exp(-2.0 * mu * b / sigma ** 2))


def same_session(barriers_pct):
    """Realised R per session per barrier, with a forced close at the bell."""
    bars = DS.load_bars()
    grids = {}
    for s_, g in track(list(bars.groupby("session", sort=True)), label="paths"):
        gr = DS.session_grid(g)
        if gr:
            grids[pd.Timestamp(s_)] = gr
    keys = sorted(grids)
    idx = pd.DatetimeIndex(keys)
    df = pd.DataFrame({"d": idx})
    g = df.groupby([df.d.dt.year, df.d.dt.month])
    tdom = g.cumcount().to_numpy() + 1
    rev = g.cumcount(ascending=False).to_numpy() + 1
    window = (tdom <= 3) & (rev != 1)

    out = {}
    for b in barriers_pct:
        R, resolved = [], []
        for k in keys:
            s = grids[k]
            op = s["open"][0]
            dist = op * b / 100.0
            hi, lo, cl = s["high"], s["low"], s["close"]
            m_tp = hi >= op + dist
            m_sl = lo <= op - dist
            INF = 1 << 30
            i_tp = int(np.argmax(m_tp)) if m_tp.any() else INF
            i_sl = int(np.argmax(m_sl)) if m_sl.any() else INF
            if i_tp == INF and i_sl == INF:
                R.append((cl[-1] - op) / dist)
                resolved.append(False)
            else:
                R.append(1.0 if i_tp < i_sl else -1.0)
                resolved.append(True)
        out[b] = dict(R=np.array(R), resolved=np.array(resolved), window=window)
    return out


def main():
    bars = DS.load_bars()
    oc = []
    for _, g in bars.groupby("session", sort=True):
        s = DS.session_grid(g)
        if s:
            oc.append(float(s["close"][-1]) / float(s["open"][0]) - 1.0)
    sigma = float(np.std(oc, ddof=1) * 100)
    print(f"\n{len(oc)} sessions, daily open-to-close sigma {sigma:.4f}%, "
          f"planning price {PRICE:,.0f}, risk pinned at ${RISK_USD:,.0f}\n")

    configs = []
    for n in (1, 2, 3, 4, 5, 8, 10, 20):
        notional = n * MNQ_PER_POINT * PRICE
        configs.append((f"{n} MNQ", n, MNQ_PER_POINT, notional,
                        RISK_USD / notional * 100))
    for n in (1, 2):
        notional = n * NQ_PER_POINT * PRICE
        configs.append((f"{n} NQ", n, NQ_PER_POINT, notional,
                        RISK_USD / notional * 100))
    configs = [c for c in configs if c[4] <= 4.0]
    res = same_session(sorted({round(c[4], 3) for c in configs}))

    print(f"{'position':>9} {'notional':>11} {'stop %':>7} {'stop pts':>9} "
          f"{'modelWR':>8} {'BE':>7} {'res':>6} {'EV$ ctrl meas':>14} "
          f"{'EV$ win model':>14} {'EV$ win meas':>13}")
    out = []
    for name, n, per_pt, notional, b in sorted(configs, key=lambda x: x[4]):
        pts = b / 100 * PRICE
        cost = (MNQ_COMM if "MNQ" in name else NQ_COMM) * n + TICK * per_pt * n
        blk = res[round(b, 3)]
        R, w = blk["R"], blk["window"]
        r1 = float(blk["resolved"].mean())
        be = 0.5 + cost / (2 * RISK_USD)
        p_win = p_up_first(DRIFT_PCT, sigma, b)
        ev_c_meas = float(R[~w].mean()) * RISK_USD - cost
        ev_w_meas = float(R[w].mean()) * RISK_USD - cost
        ev_w_model = ((2 * p_win - 1) * RISK_USD * r1
                      + (1 - r1) * (DRIFT_PCT / 100) * notional - cost)
        print(f"{name:>9} {notional:>11,.0f} {b:>7.3f} {pts:>9.1f} "
              f"{p_win:>8.4f} {be:>7.4f} {r1:>6.1%} {ev_c_meas:>+14.2f} "
              f"{ev_w_model:>+14.2f} {ev_w_meas:>+13.2f}")
        out.append(dict(position=name, contracts=n, notional=notional,
                        stop_pct=b, stop_points=pts, cost_usd=cost,
                        model_wr=p_win, breakeven=be, resolve_same_session=r1,
                        ev_control_measured=ev_c_meas,
                        ev_window_model=ev_w_model,
                        ev_window_measured=ev_w_meas,
                        n_window=int(w.sum()), n_control=int((~w).sum())))

    df = pd.DataFrame(out)
    df.to_csv(C.DATA / "reports" / "micro_contract_leverage.csv", index=False)
    print(f"\nwindow n={int(df.n_window.iloc[0])}, control n={int(df.n_control.iloc[0])}. "
          "The measured window column is far too small to decide anything and "
          "is a consistency check only.")

    # a configuration that cannot finish inside the session is not a trade
    ok = df[df.resolve_same_session >= 0.90]
    best = ok.loc[ok.ev_window_model.idxmax()] if len(ok) else df.iloc[0]
    print(f"\nrestricting to configurations that resolve in-session at least "
          f"90% of the time, which the flat-by-16:45 rule forces:")
    print(f"  best: {best.position}, stop {best.stop_points:.0f} points, "
          f"resolves {best.resolve_same_session:.1%}, model WR {best.model_wr:.4f} "
          f"vs breakeven {best.breakeven:.4f}, EV ${best.ev_window_model:+.2f}")
    r = df[df.position == "1 NQ"].iloc[0]
    print(f"  vs 1 NQ: stop {r.stop_points:.0f} points, model WR {r.model_wr:.4f}, "
          f"EV ${r.ev_window_model:+.2f}  -> gain "
          f"${best.ev_window_model - r.ev_window_model:+.2f} per trade")
    print(f"\nwrote {C.DATA / 'reports' / 'micro_contract_leverage.csv'}")


if __name__ == "__main__":
    main()
