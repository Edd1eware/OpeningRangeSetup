"""Alternative EXIT policies on the same frozen signals.

Pre-registered. Every policy and threshold below is fixed before the first run.

Why this exists
---------------
Codex's round-4 answer to "is there any remaining estimand on disk that could
still carry an edge": the honest answer is NOT "none". His words:

    a finite set of terminal means and six stopped means does not characterise
    the entire conditional path distribution. Your negative result attaches to
    the tested policies, not every strategy using those three signal families.

and he named what was missing: trailing or break-even exits, exits conditional
on subsequent flow, volatility-scaled barriers, and longer holding periods that
the existing data already support. This script measures exactly that list and
nothing else. It is not a sweep: six policies, declared here, each tied to a
mechanism, all reported whatever they do.

The six policies, frozen
------------------------
P1  fixed 20/20                      baseline, so the others are comparable
P2  break-even at +10, SL 20, TP 40  "protect the trade once it pays for itself"
P3  trail: SL 20, activate +20, D 10 "let a runner run"
P4  vol-scaled: SL = TP = sigma      sigma = trailing-60s print range, clipped
                                     to [8, 60] ticks. Tests whether a FIXED
                                     bracket was the thing that was wrong
P5  flow exit: SL 20, TP 40, plus exit at market when the trailing-15s aggressor
                                     imbalance flips against the position
P6  long hold: SL 20, TP 40, horizon 1800s instead of 300s

Causality, the thing that is easy to get wrong here
---------------------------------------------------
A moving stop must be set from PRIOR prints only. The running favourable
maximum is therefore shifted by one print before the stop level is computed, so
the stop that a print is tested against never knows that print's own extreme.
Getting this wrong is the same class of error as the displacement lookahead
Codex found in script 18.

P4's sigma is measured over [tau-60s, tau) and P5's flow checks use closed 15s
windows strictly before each check instant, so neither reaches forward.

Honest accounting
-----------------
* Primary outcome is NET ticks with a session-level cluster bootstrap, as in
  script 21. No binomial tests: payouts are variable by construction here.
* m = 3 families x 6 policies = 18 cells, and the reported interval IS the
  (1 - 0.05/18) one, computed from 50,000 replicates. As Codex noted, that
  adjustment covers THIS grid; it does not retroactively correct the project's
  whole adaptive research history, and this script does not pretend otherwise.
* P6 can only use decisions with tau <= 1799.5s, because the tape ends at
  10:30. That roughly halves its sample and the tables say so.
* The prior is low: three families already produced nothing under 18 bracket
  policies and 18 markout cells. A positive cell here would need to survive a
  fresh season before it meant anything, and 2026 cannot provide one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATA, NY  # noqa: E402
from progress import track  # noqa: E402
from tape_lib import NS, IS_SESSIONS, TAIL_Q, WIN_FROM_S, WIN_TO_S, SessionTape  # noqa: E402

TAPE = DATA / "tape" / "tape_trades_2026.parquet"
DEC = DATA / "tape" / "decisions_15s.parquet"
OUT = DATA / "reports" / "exit_policies.csv"

ENTRY_DELAY_S = 0.5
COSTS = (1.8, 2.8, 3.8)
N_BOOT = 50_000
SEED = 20261012
ADVANCE_BAR = 2.5
VOL_WIN_S = 60
VOL_CLIP = (8, 60)
FLOW_STEP_S = 15

# name -> dict(sl, tp or None, be, act, trail, horizon, flow)
POLICIES = {
    "P1_fixed_20_20":  dict(sl=20, tp=20,  be=None, act=None, trail=None, hor=300,  flow=False, vol=False),
    "P2_breakeven_10": dict(sl=20, tp=40,  be=10,   act=None, trail=None, hor=300,  flow=False, vol=False),
    "P3_trail_20_10":  dict(sl=20, tp=None, be=None, act=20,  trail=10,   hor=300,  flow=False, vol=False),
    "P4_vol_scaled":   dict(sl=None, tp=None, be=None, act=None, trail=None, hor=300, flow=False, vol=True),
    "P5_flow_exit":    dict(sl=20, tp=40,  be=None, act=None, trail=None, hor=300,  flow=True,  vol=False),
    "P6_long_hold":    dict(sl=20, tp=40,  be=None, act=None, trail=None, hor=1800, flow=False, vol=False),
}


def walk_policy(st: SessionTape, i: int, d: int, p: dict, sl: int, tp: int | None,
                t_limit_ns: int, flow_deadline_ns: int | None) -> tuple[float, int, str]:
    """Walk from the entry print under a possibly MOVING stop.

    Returns (gross ticks, exit index, kind). The fill is the crossing print's
    own excursion, so overshoot is included on both sides -- a defined proxy,
    not a uniformly pessimistic convention.
    """
    e = st.px[i]
    j_end = int(np.searchsorted(st.ts, t_limit_ns, side="right"))
    if j_end <= i + 1:
        return 0.0, i, "no_path"

    seg = st.px[i + 1:j_end]
    fav = d * (seg - e)                       # favourable excursion, in ticks

    # stop level, in favourable-excursion space, from PRIOR prints only
    run = np.maximum.accumulate(fav)
    prev = np.concatenate([[-np.inf], run[:-1]])

    stop = np.full(len(fav), -float(sl))
    if p["be"] is not None:
        stop = np.where(prev >= p["be"], 0.0, stop)
    if p["act"] is not None:
        stop = np.where(prev >= p["act"],
                        np.maximum(-float(sl), prev - float(p["trail"])), stop)

    hit = fav <= stop
    if tp is not None:
        hit = hit | (fav >= tp)

    k = int(np.argmax(hit)) if hit.any() else -1
    j_barrier = i + 1 + k if k >= 0 else -1

    # a flow exit only matters if it fires BEFORE the barrier
    j_flow = -1
    if flow_deadline_ns is not None:
        jf = int(np.searchsorted(st.ts, flow_deadline_ns, side="left"))
        if i + 1 <= jf < j_end:
            j_flow = jf

    if j_barrier >= 0 and (j_flow < 0 or j_barrier <= j_flow):
        return float(d * (st.px[j_barrier] - e)), j_barrier, "barrier"
    if j_flow >= 0:
        return float(d * (st.px[j_flow] - e)), j_flow, "flow"

    j = j_end - 1
    return float(d * (st.px[j] - e)), j, "timeout"


def flow_flip_time(st: SessionTape, t0_ns: int, d: int, t_limit_ns: int) -> int | None:
    """First 15s window, strictly after entry, whose aggressor imbalance has
    flipped against the position. Each window is closed before it is used."""
    step = int(FLOW_STEP_S * NS)
    t = t0_ns + step
    while t <= t_limit_ns:
        imb, tot = st.imbalance(np.array([t - step]), np.array([t]))
        if tot[0] > 0 and d * imb[0] < 0:
            return int(t)
        t += step
    return None


def boot_ci(sums: np.ndarray, cnts: np.ndarray, rng: np.random.Generator,
            levels: tuple[float, ...]) -> dict[float, tuple[float, float]]:
    n = len(sums)
    idx = rng.integers(0, n, size=(N_BOOT, n))
    s = sums[idx].sum(axis=1)
    c = cnts[idx].sum(axis=1)
    m = s[c > 0] / c[c > 0]
    return {lv: (float(np.quantile(m, (1 - lv) / 2)),
                 float(np.quantile(m, 1 - (1 - lv) / 2))) for lv in levels}


def main() -> None:
    print("loading tape...", flush=True)
    tape = pd.read_parquet(TAPE)
    ny = pd.to_datetime(tape["ts_ns"], utc=True).dt.tz_convert(NY)
    secs = (ny.dt.hour * 3600 + ny.dt.minute * 60 + ny.dt.second
            + ny.dt.microsecond / 1e6) - 9.5 * 3600
    tape = tape[(secs >= WIN_FROM_S) & (secs < WIN_TO_S)].reset_index(drop=True)

    groups: dict = {}
    for sess, g in tape.groupby("session", sort=True):
        open_ts = pd.Timestamp(sess).tz_localize(NY) + pd.Timedelta(hours=9, minutes=30)
        groups[sess] = SessionTape(g, int(open_ts.tz_convert("UTC").value))
    all_sessions = np.array(sorted(groups.keys()))

    stamp = DEC.with_suffix(".fingerprint")
    if not stamp.exists():
        raise SystemExit("decision table has no fingerprint; rerun script 18")
    print(f"decision table fingerprint {stamp.read_text(encoding='utf-8').strip()}",
          flush=True)

    dec_full = pd.read_parquet(DEC)
    sessions = np.array(sorted(dec_full["session"].unique()))
    is_set = set(sessions[:IS_SESSIONS])
    is_full = dec_full["session"].isin(is_set).to_numpy()

    # thresholds frozen on the FULL IS population, as script 18 froze them
    tail_cut = float(np.quantile(np.abs(dec_full.loc[is_full, "imb"].to_numpy()), TAIL_Q))
    vol_hi = float(np.quantile(dec_full.loc[is_full, "vol"].to_numpy(), 0.90))
    disp_lo = float(np.quantile(dec_full.loc[is_full, "abs_disp"].to_numpy(), 0.25))
    disp_hi = float(np.quantile(dec_full.loc[is_full, "abs_disp"].to_numpy(), 0.75))

    dom = np.sign(dec_full["imb"].to_numpy())
    hv = dec_full["vol"].to_numpy() >= vol_hi
    families = {
        "imb_tail":   (np.abs(dec_full["imb"].to_numpy()) >= tail_cut, dom),
        "absorption": (hv & (dec_full["abs_disp"].to_numpy() <= disp_lo), -dom),
        "drive":      (hv & (dec_full["abs_disp"].to_numpy() >= disp_hi), dom),
    }

    m_cells = len(families) * len(POLICIES)
    adj = 1.0 - 0.05 / m_cells
    print(f"cells = {m_cells}; reporting the {adj:.4%} interval "
          f"(adjusted, applied)", flush=True)
    print(f"frozen: |imb| >= {tail_cut:.4f}; vol >= {int(np.ceil(vol_hi))}; "
          f"|disp| <= {disp_lo:.0f} / >= {disp_hi:.0f}", flush=True)

    rng = np.random.default_rng(SEED)
    rows = []

    cells = [(f, p) for f in families for p in POLICIES]
    for fam, pname in track(cells, label="exit policies"):
        p = POLICIES[pname]
        mask, direction = families[fam]
        last_tau = WIN_TO_S - p["hor"] - ENTRY_DELAY_S - 1.0
        sel = mask & (direction != 0) & (dec_full["tau_s"].to_numpy() <= last_tau)
        sub = dec_full[sel].copy()
        sub["d"] = direction[sel]
        sub = sub.sort_values(["session", "tau_s"])
        if len(sub) < 30:
            continue

        recs = []
        for sess, g in sub.groupby("session", sort=True):
            st = groups.get(sess)
            if st is None:
                continue
            busy = -1
            for r in g.itertuples():
                e_ns = st.open_ns + int(r.tau_s * NS) + int(ENTRY_DELAY_S * NS)
                if e_ns < busy:
                    continue
                i = int(np.searchsorted(st.ts, e_ns, side="left"))
                if i >= len(st.ts):
                    continue
                t_limit = st.ts[i] + int(p["hor"] * NS)
                if t_limit > st.open_ns + int(WIN_TO_S * NS):
                    continue

                sl, tp = p["sl"], p["tp"]
                if p["vol"]:
                    # sigma = print RANGE over [tau-60s, tau), clipped. Measured
                    # strictly before the decision, so no lookahead.
                    t1 = st.open_ns + int(r.tau_s * NS)
                    a = int(np.searchsorted(st.ts, t1 - int(VOL_WIN_S * NS), "left"))
                    b = int(np.searchsorted(st.ts, t1, "left"))
                    if b - a < 5:
                        continue
                    rng_t = int(st.px[a:b].max() - st.px[a:b].min())
                    sl = tp = int(np.clip(rng_t, *VOL_CLIP))

                fd = (flow_flip_time(st, st.ts[i], int(r.d), t_limit)
                      if p["flow"] else None)
                gross, j, kind = walk_policy(st, i, int(r.d), p, sl, tp, t_limit, fd)
                if kind == "no_path":
                    continue
                busy = t_limit if kind == "timeout" else st.ts[j]
                recs.append((sess, gross, int(r.d), kind, sl))

        if len(recs) < 30:
            continue
        rec = pd.DataFrame(recs, columns=["session", "ticks", "d", "kind", "sl_used"])

        for sample in ("ALL", "IS", "OOS"):
            if sample == "ALL":
                t, slist = rec, all_sessions
            elif sample == "IS":
                t = rec[rec["session"].isin(is_set)]
                slist = np.array(sorted(is_set))
            else:
                t = rec[~rec["session"].isin(is_set)]
                slist = np.array([s for s in all_sessions if s not in is_set])
            if len(t) < 30:
                continue
            gross = t["ticks"].to_numpy()
            gb = t.groupby("session")["ticks"].agg(["sum", "count"])
            sums = np.array([float(gb["sum"].get(s, 0.0)) for s in slist])
            cnts = np.array([float(gb["count"].get(s, 0)) for s in slist])

            for c in COSTS:
                ci = boot_ci(sums - c * cnts, cnts, rng, (0.95, adj))
                lo = t[t["d"] > 0]["ticks"].to_numpy() - c
                sh = t[t["d"] < 0]["ticks"].to_numpy() - c
                rows.append(dict(
                    family=fam, policy=pname, sample=sample, cost=c,
                    n=len(t), n_sessions=int((cnts > 0).sum()),
                    trades_per_active=float(cnts[cnts > 0].mean()),
                    wr=float((gross > 0).mean()),
                    gross_ev=float(gross.mean()), net_ev=float(gross.mean() - c),
                    lo95=ci[0.95][0], hi95=ci[0.95][1],
                    lo_adj=ci[adj][0], hi_adj=ci[adj][1],
                    dir_balanced=float((lo.mean() + sh.mean()) / 2) if len(lo) and len(sh) else np.nan,
                    drift_estimate=float((lo.mean() - sh.mean()) / 2) if len(lo) and len(sh) else np.nan,
                    median_sl=float(np.median(t["sl_used"])),
                    n_timeout=int((t["kind"] == "timeout").sum()),
                    n_flow=int((t["kind"] == "flow").sum()),
                ))

    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    print("", flush=True)
    print("=" * 118, flush=True)
    print("POLITICAS DE SALIDA alternativas. Primario = EV NETO en ticks, "
          "incertidumbre a nivel sesion.", flush=True)
    print("", flush=True)
    base = out[out["cost"].eq(1.8)]
    for fam in families:
        print(f"--- {fam}, costo 1.8 ---", flush=True)
        print("| politica | muestra | n | trades/ses | WR | EV bruto | EV neto | "
              f"IC95 | IC{adj:.2%} | balanceado dir | SL med | timeout | flow |",
              flush=True)
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|", flush=True)
        for r in base[base["family"].eq(fam)].sort_values(["policy", "sample"]).itertuples():
            print(f"| {r.policy} | {r.sample} | {r.n:,} | {r.trades_per_active:.1f} | "
                  f"{r.wr:.1%} | {r.gross_ev:+.2f} | **{r.net_ev:+.2f}** | "
                  f"[{r.lo95:+.2f}, {r.hi95:+.2f}] | "
                  f"[{r.lo_adj:+.2f}, {r.hi_adj:+.2f}] | {r.dir_balanced:+.2f} | "
                  f"{r.median_sl:.0f} | {r.n_timeout} | {r.n_flow} |", flush=True)
        print("", flush=True)

    print(f"VEREDICTO: avanza solo si la cota inferior AJUSTADA OOS supera "
          f"{ADVANCE_BAR} ticks netos", flush=True)
    print("", flush=True)
    any_pass = False
    for c in COSTS:
        s = out[out["cost"].eq(c) & out["sample"].eq("OOS")]
        if not len(s):
            continue
        b = s.loc[s["lo_adj"].idxmax()]
        ok = bool(b["lo_adj"] > ADVANCE_BAR)
        any_pass |= ok
        print(f"  costo {c}: mejor cota inferior ajustada = {b['lo_adj']:+.3f} "
              f"({b['family']} {b['policy']}) -> "
              f"{'AVANZA' if ok else 'NO avanza'}", flush=True)
        inc = s[s["hi_adj"] > ADVANCE_BAR]
        print(f"      cotas SUPERIORES que excluyen {ADVANCE_BAR}: "
              f"{len(s) - len(inc)} de {len(s)}", flush=True)
        for r in inc.itertuples():
            print(f"      INCONCLUSA: {r.family} {r.policy} neto {r.net_ev:+.3f} "
                  f"ajustado [{r.lo_adj:+.3f}, {r.hi_adj:+.3f}] (n={r.n})",
                  flush=True)
    print("", flush=True)
    print(f"  CONCLUSION: {'hay celda que avanza' if any_pass else 'NINGUNA celda avanza'}",
          flush=True)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
