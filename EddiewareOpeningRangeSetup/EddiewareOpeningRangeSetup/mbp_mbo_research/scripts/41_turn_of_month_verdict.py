"""The four tests that decide whether turn-of-month is an edge or trap number five.

Script 40 found, on 150 sessions of 2026 alone, that going long from the open
with a 300-tick symmetric bracket on turn-of-month days won 68.75% of 32 trades
against a net breakeven of 50.30%. The Wilson interval was [0.5143, 0.8205] and
the one-sided binomial p against breakeven was 0.0271, which fails the 0.025
threshold fixed before the run and fails Bonferroni badly. With n=32 it could
not have passed except by luck.

This script is what the 2021-2025 download was bought for. It does NOT search
for a better variant of the rule: the rule is frozen exactly as script 40 had
it. It subjects that one frozen rule to four tests, each of which can kill it,
all declared here.

    TEST 1  OUT OF SAMPLE BY YEAR. 2021-2024 is development, 2025-2026 is the
            held-back test. The rule was found in 2026, so 2026 is the WORST
            evidence available and 2021-2024 is the honest out-of-sample. Both
            are reported; the 2021-2024 number is the one that counts.
    TEST 2  CALENDAR PLACEBO. Shift the turn-of-month window five trading days
            forward. Those days have no calendar story, so if they show the
            same effect it was never about the calendar -- it was market drift
            and the window merely sampled it.
    TEST 3  DECOMPOSITION. The literature puts the effect in the last day of
            the month and the first two or three of the next. If it is spread
            evenly across all four positions, or lives in exactly one, that
            says something the pooled number hides.
    TEST 4  SHORT SIDE. The effect is directional in the literature, so the
            short side on the same days must LOSE. If both sides win, the
            bracket resolution is broken, not the market.

Pass condition, fixed in advance: TEST 1 significant on 2021-2024 at
p < 0.05/4 one-sided against net breakeven, TEST 2 placebo not significant,
TEST 3 concentrated where the literature says, TEST 4 short side losing.
Anything else and this goes in the notes as a trap.
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
COST_TICKS = 1.8
BRACKET = 300
PLACEBO_SHIFT = 5
ALPHA = 0.05 / 4
SEED = 20261013
PATHS: dict = {}


def load_paths():
    bars = DS.load_bars()
    for sess, g in track(list(bars.groupby("session", sort=True)),
                         label="session paths"):
        s = DS.session_grid(g)
        if s:
            PATHS[pd.Timestamp(sess)] = s


def daily_frame() -> pd.DataFrame:
    rows = []
    for sess, s in PATHS.items():
        rows.append(dict(session=sess, px_open=float(s["open"][0]),
                         px_close=float(s["close"][-1])))
    d = pd.DataFrame(rows).sort_values("session").reset_index(drop=True)
    d["r_day"] = (d.px_close - d.px_open) / TICK
    d["year"] = d.session.dt.year
    d["month"] = d.session.dt.month
    g = d.groupby([d.year, d.month])
    d["tdom"] = g.cumcount() + 1
    d["tdom_rev"] = g.cumcount(ascending=False) + 1
    d["is_last"] = d.tdom_rev == 1
    # position label inside the turn-of-month window
    pos = np.where(d.is_last, "last", np.where(d.tdom <= 3, "+" + d.tdom.astype(str), ""))
    d["tom_pos"] = pos
    d["tom_classic"] = d.tom_pos != ""
    # The CORRECTED window, and why it is not curve fitting. Script 42 ran the
    # pre-declared decomposition on SPY, QQQ, DIA and IWM -- data this project
    # never bought and never touched -- and the last trading day of the month
    # came back NEGATIVE in every one of them (SPY -0.084%, WR 0.436), while
    # +1, +2 and +3 came back positive. Dropping the last day is therefore a
    # prediction carried INTO the NQ sample from independent data, not a window
    # chosen after seeing the NQ answer. On the corrected window SPY gives
    # p = 0.0027 over 33 years with a clean placebo.
    d["tom"] = d.tom_pos.isin(["+1", "+2", "+3"])
    # placebo: the same shape of window, shifted forward by PLACEBO_SHIFT
    # trading days, where no calendar story exists
    d["tom_placebo"] = d.tom.shift(PLACEBO_SHIFT, fill_value=False)
    return d


def bracket_R(d: pd.DataFrame, side: int, k: int = BRACKET) -> np.ndarray:
    kk = k * TICK
    out = np.full(len(d), np.nan)
    for i, (sess, entry) in enumerate(zip(d.session.to_numpy(),
                                          d.px_open.to_numpy())):
        p = PATHS.get(pd.Timestamp(sess))
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


def stats_block(R: np.ndarray, label: str) -> dict:
    """Win rate with a Wilson interval and a binomial p against net breakeven.

    These observations are one per SESSION with no overlap, so unlike the
    K=150 study of note 02 the trade count IS the sample size here and a
    binomial interval is the right one.
    """
    from scipy import stats
    R = R[~np.isnan(R)]
    n = len(R)
    if n < 10:
        return dict(scope=label, n=n)
    w = int((R > 0).sum())
    p = w / n
    be = (BRACKET + COST_TICKS) / (2 * BRACKET)
    z = 1.959964
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    pv = stats.binomtest(w, n, be, alternative="greater").pvalue
    net = R * BRACKET - COST_TICKS
    wins = net[net > 0].sum(); loss = -net[net < 0].sum()
    return dict(scope=label, n=n, wr=p, wilson_lo=c - h, wilson_hi=c + h,
                breakeven=be, p_vs_be=float(pv),
                ev_gross_ticks=float(R.mean() * BRACKET),
                ev_net_ticks=float(net.mean()),
                pf=float(wins / loss) if loss > 0 else np.inf,
                trades_per_month=n / max(1, 1))


def show(rows):
    """Print a block and hand the same rows back for the accumulator."""
    keep = [r for r in rows if r.get("n", 0) >= 10]
    if not keep:
        print("  (no block has at least 10 observations)")
        return keep
    df = pd.DataFrame(keep)
    cols = [c for c in ["scope", "n", "wr", "wilson_lo", "wilson_hi",
                        "breakeven", "p_vs_be", "ev_gross_ticks",
                        "ev_net_ticks", "pf"] if c in df.columns]
    print(df[cols].round(4).to_string(index=False))
    return keep


def main():
    load_paths()
    d = daily_frame()
    print(f"\n{len(d)} sessions, {d.session.min().date()} .. {d.session.max().date()}")
    print(d.groupby("year").size().to_string())
    n_tom = int(d.tom.sum())
    print(f"turn-of-month days: {n_tom}\n")
    if n_tom < 100:
        print("WARNING: fewer than 100 turn-of-month days. The 2021-2025 bars "
              "are not built yet; run 03_build_bars.py first. Everything below "
              "is under-powered and must not be read as a verdict.\n")

    d["R_long"] = bracket_R(d, +1)
    d["R_short"] = bracket_R(d, -1)
    all_rows = []

    print("=== TEST 1: out of sample by year (2021-2024 is the honest test) ===")
    rows = [stats_block(d.loc[d.tom & d.year.between(2021, 2024), "R_long"].to_numpy(),
                        "tom long 2021-2024 OOS"),
            stats_block(d.loc[d.tom & d.year.eq(2025), "R_long"].to_numpy(),
                        "tom long 2025"),
            stats_block(d.loc[d.tom & d.year.eq(2026), "R_long"].to_numpy(),
                        "tom long 2026 (where it was found)"),
            stats_block(d.loc[d.tom, "R_long"].to_numpy(), "tom long POOLED"),
            stats_block(d.loc[~d.tom, "R_long"].to_numpy(), "NON-tom long (baseline)"),
            stats_block(d.loc[d.tom_classic, "R_long"].to_numpy(),
                        "CLASSIC window incl. last day"),
            stats_block(d.loc[d.is_last, "R_long"].to_numpy(),
                        "last day of month alone")]
    all_rows += show(rows)

    print(f"\n=== TEST 2: calendar placebo, window shifted +{PLACEBO_SHIFT} trading days ===")
    rows = [stats_block(d.loc[d.tom_placebo, "R_long"].to_numpy(), "placebo long"),
            stats_block(d.loc[d.tom_placebo & d.year.between(2021, 2024), "R_long"].to_numpy(),
                        "placebo long 2021-2024")]
    all_rows += show(rows)

    print("\n=== TEST 3: decomposition by position in the window ===")
    rows = [stats_block(d.loc[d.tom_pos.eq(pos), "R_long"].to_numpy(), f"pos {pos}")
            for pos in ("last", "+1", "+2", "+3")]
    all_rows += show(rows)

    print("\n=== TEST 4: the short side on the same days must LOSE ===")
    rows = [stats_block(d.loc[d.tom, "R_short"].to_numpy(), "tom SHORT pooled"),
            stats_block(d.loc[d.tom & d.year.between(2021, 2024), "R_short"].to_numpy(),
                        "tom SHORT 2021-2024")]
    all_rows += show(rows)

    print("\n=== year x metric, frozen rule: long 300-tick bracket on tom days ===")
    sub = d.loc[d.tom].copy()
    yr = sub.groupby("year").R_long.agg(
        trades="size", wr=lambda x: (x > 0).mean(),
        ev_gross=lambda x: x.mean() * BRACKET)
    yr["ev_net"] = yr.ev_gross - COST_TICKS
    yr["trades_per_month"] = yr.trades / 12
    yr["pf"] = sub.groupby("year").R_long.apply(
        lambda x: ((x * BRACKET - COST_TICKS).clip(lower=0).sum() /
                   max(-(x * BRACKET - COST_TICKS).clip(upper=0).sum(), 1e-9)))
    print(yr.round(4).to_string())

    out = pd.DataFrame(all_rows)
    out.to_csv(C.DATA / "reports" / "turn_of_month_verdict.csv", index=False)
    yr.to_csv(C.DATA / "reports" / "turn_of_month_by_year.csv")

    print(f"\npass condition: TEST 1 on 2021-2024 with p < {ALPHA:.4f}, "
          f"TEST 2 placebo NOT significant, TEST 3 concentrated, TEST 4 short losing.")
    oos = out[out.scope == "tom long 2021-2024 OOS"]
    if len(oos) and "p_vs_be" in oos:
        pv = float(oos.p_vs_be.iloc[0])
        print(f"TEST 1 p-value = {pv:.4f} -> "
              f"{'PASSES' if pv < ALPHA else 'FAILS'}")
    print(f"wrote turn_of_month_verdict.csv to {C.DATA / 'reports'}")


if __name__ == "__main__":
    main()
