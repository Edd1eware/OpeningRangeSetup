"""First-passage barrier study: the estimand the markout does NOT bound.

Pre-registered. Every parameter below is frozen before the first run, and the
IS/OOS roles are unchanged from the earlier studies.

Why this exists
---------------
Script 17/18 measured fixed-horizon markouts and found nothing that pays. I
then treated that as a gate and closed the path. Codex rejected the gate, and
he is right. His counterexample:

    after a signal, 60% of paths reach +10 first and 40% reach -10 first, and
    all of them return to zero by 15 seconds.
    -> the 15-second markout is exactly 0
    -> a symmetric first-passage exit earns +2 ticks GROSS

So "no markout, therefore no barrier engine" is a research-budget rule, not a
theorem. First-passage asymmetry is a DIFFERENT estimand and it is the one a
bracket strategy actually harvests. It is also the one the Lucid objective
needs, because it produces an EV per trade with a real stop.

What this does NOT claim
------------------------
Stopping a martingale does not create positive gross expectancy. If the signal
carries no information AND the path is a martingale, this measures zero. The
point is that the markout being zero does not establish the martingale
property of the whole intervening path, which is what would be needed.

The null, and why it is exactly zero here
-----------------------------------------
For a SYMMETRIC bracket on a given path with a given entry price, the opposite
direction's outcome is the exact negative: whichever print first crosses
entry+K is the long's TP fill and the short's SL fill, at the SAME price, so
overshoot included, follow + fade = 0 exactly. Timeout marks are likewise
antisymmetric. So the random-direction null is 0 by construction.

Codex's caveat is accepted and handled rather than waved away: sign(imb) is not
randomised, so DRIFT in the selected sample can bias the signed mean if the
long/short mix is imbalanced. His own decomposition found longs positive and
shorts negative in both terminal-sign strata, i.e. upward drift in these
observations. Therefore this script ALWAYS reports:
  * the long and short legs separately,
  * the long/short mix, so an imbalanced mix cannot hide,
  * and the drift-neutral contrast (long leg - short leg) / 2.
Drift cancels only when the mix is balanced; the tables make that checkable
instead of assumed.

What was fixed before running this
----------------------------------
* The displacement feature used `idx_at` (first print at or AFTER the decision
  instant), which is lookahead. Now `idx_before`. Codex found it; it moved 122
  absorption and 109 drive selection flags.
* The cached decision table now carries a fingerprint of the code that built
  it, so a correction cannot silently leave stale features behind.

Honest statistics, after Codex's "Bonferroni is printed, not implemented"
-------------------------------------------------------------------------
The primary outcome is NET P&L in ticks with session-level uncertainty. There is
no binomial test anywhere: payouts are variable here (overshoot on the crossing
print, mark-to-market timeouts), and a win-rate test against (K+c)/(T+S) is
invalid under variable payouts.

Multiple testing is ACTUALLY applied, not announced: with m cells the reported
interval is a (1 - 0.05/m) bootstrap interval, not a 95% one. The 95% interval
is printed beside it for reference. The bootstrap resamples SESSIONS and is
computed from per-session sums and counts, so 50,000 replicates are cheap
enough to resolve the adjusted tail.

Sessions with zero signals are included in the per-session account economics,
because daily opportunity frequency is what the evaluation actually consumes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATA, NY  # noqa: E402
from progress import track  # noqa: E402
from tape_lib import (  # noqa: E402
    NS, IS_SESSIONS, TAIL_Q, WIN_FROM_S, WIN_TO_S, SessionTape,
)

TAPE = DATA / "tape" / "tape_trades_2026.parquet"
DEC = DATA / "tape" / "decisions_15s.parquet"
OUT = DATA / "reports" / "barrier_engine.csv"
OUT_SESS = DATA / "reports" / "barrier_per_session.csv"

# ---- frozen policy ---------------------------------------------------------
ENTRY_DELAY_S = 0.5        # decision at tau, entry at the first print >= tau+0.5s
HORIZON_S = 300            # 5 minutes, then mark to market at the last print
BRACKETS = ((8, 8), (12, 12), (20, 20), (40, 40), (10, 20), (20, 40))  # (SL, TP)
COSTS = (1.8, 2.8, 3.8)    # 1.8 is optimistic; the others are Codex's stress
N_BOOT = 50_000
SEED = 20261012
ADVANCE_BAR = 2.5          # net ticks/trade the Lucid work says is needed

# the grid must leave room for delay + horizon inside the tape
LAST_TAU_S = WIN_TO_S - HORIZON_S - ENTRY_DELAY_S - 1.0


def walk_one(ts: np.ndarray, px: np.ndarray, i_entry: int, d: int,
             sl: int, tp: int, t_limit_ns: int) -> tuple[float, int, str]:
    """Walk the tape from the entry print. Returns (ticks_gross, exit_idx, kind).

    Fill is at the CROSSING PRINT's price, not at the barrier level. This is a
    DEFINED PROXY, not a uniformly pessimistic convention: stop overshoot hurts
    us, target overshoot helps us. Codex corrected my earlier description of it
    as "overshoot is paid by us", which is only half true.
    """
    entry_px = px[i_entry]
    up = entry_px + (tp if d > 0 else sl)
    dn = entry_px - (sl if d > 0 else tp)

    j_end = np.searchsorted(ts, t_limit_ns, side="right")
    if j_end <= i_entry + 1:
        return 0.0, i_entry, "no_path"

    seg = px[i_entry + 1:j_end]
    hit = (seg >= up) | (seg <= dn)
    k = int(np.argmax(hit)) if hit.any() else -1

    if k < 0:
        # timeout: mark to market at the last print inside the horizon
        j = j_end - 1
        return float(d * (px[j] - entry_px)), j, "timeout"

    j = i_entry + 1 + k
    return float(d * (px[j] - entry_px)), j, "barrier"


def run_family(tape_groups: dict, dec: pd.DataFrame, mask: np.ndarray,
               direction: np.ndarray, sl: int, tp: int) -> pd.DataFrame:
    """One pass per (family, bracket): walk every selected decision in time
    order, enforcing ONE POSITION AT A TIME inside each session."""
    rows = []
    sub = dec[mask & (direction != 0)].copy()
    sub["d"] = direction[mask & (direction != 0)]
    sub = sub.sort_values(["session", "tau_s"])

    for sess, g in sub.groupby("session", sort=True):
        st = tape_groups.get(sess)
        if st is None:
            continue
        open_ns = st.open_ns
        busy_until = -1  # ns; a new entry before this is skipped, not stacked

        for r in g.itertuples():
            tau_ns = open_ns + int(r.tau_s * NS)
            e_ns = tau_ns + int(ENTRY_DELAY_S * NS)
            if e_ns < busy_until:
                rows.append(dict(session=sess, tau_s=r.tau_s, taken=False,
                                 ticks=np.nan, kind="skipped_busy"))
                continue
            i = int(np.searchsorted(st.ts, e_ns, side="left"))
            if i >= len(st.ts):
                rows.append(dict(session=sess, tau_s=r.tau_s, taken=False,
                                 ticks=np.nan, kind="no_entry"))
                continue
            # the horizon starts at the ACTUAL entry print, so the deadline is
            # not guaranteed to sit inside the tape by the grid truncation
            # alone. Codex: max observed entry wait was 4.8s and nothing ran
            # past 10:30 on this data, but the code must assert it rather than
            # rely on the dataset.
            t_limit = st.ts[i] + int(HORIZON_S * NS)
            hard_end = open_ns + int(WIN_TO_S * NS)
            if t_limit > hard_end:
                rows.append(dict(session=sess, tau_s=r.tau_s, taken=False,
                                 ticks=np.nan, kind="past_tape_end"))
                continue
            gross, j, kind = walk_one(st.ts, st.px, i, int(r.d), sl, tp, t_limit)
            if kind == "no_path":
                rows.append(dict(session=sess, tau_s=r.tau_s, taken=False,
                                 ticks=np.nan, kind=kind))
                continue
            # A TIMEOUT holds the position until the DEADLINE, even though its
            # accounting mark comes from the last print before it. Releasing at
            # that print would free the slot early and let an overlapping
            # position be opened. Codex flagged this as a latent defect.
            busy_until = t_limit if kind == "timeout" else st.ts[j]
            rows.append(dict(session=sess, tau_s=r.tau_s, taken=True,
                             ticks=gross, kind=kind, d=int(r.d)))
    return pd.DataFrame(rows)


def boot_mean_ci(session_sums: np.ndarray, session_counts: np.ndarray,
                 rng: np.random.Generator, levels: tuple[float, ...]
                 ) -> dict[float, tuple[float, float]]:
    """Session block bootstrap of a trade-weighted mean, vectorised.

    Resampling sessions is equivalent to resampling (sum, count) pairs, so this
    is O(n_sessions) per replicate instead of O(n_trades) and 50,000 replicates
    are affordable -- which is what makes the multiple-testing-adjusted tail
    actually resolvable rather than merely announced.
    """
    n = len(session_sums)
    idx = rng.integers(0, n, size=(N_BOOT, n))
    sums = session_sums[idx].sum(axis=1)
    cnts = session_counts[idx].sum(axis=1)
    ok = cnts > 0
    means = np.full(N_BOOT, np.nan)
    means[ok] = sums[ok] / cnts[ok]
    means = means[~np.isnan(means)]
    out = {}
    for lv in levels:
        a = (1.0 - lv) / 2.0
        out[lv] = (float(np.quantile(means, a)), float(np.quantile(means, 1 - a)))
    return out


def main() -> None:
    print("loading tape...", flush=True)
    tape = pd.read_parquet(TAPE)
    ny = pd.to_datetime(tape["ts_ns"], utc=True).dt.tz_convert(NY)
    secs = (ny.dt.hour * 3600 + ny.dt.minute * 60 + ny.dt.second
            + ny.dt.microsecond / 1e6) - 9.5 * 3600
    tape = tape[(secs >= WIN_FROM_S) & (secs < WIN_TO_S)].reset_index(drop=True)

    groups = {}
    for sess, g in tape.groupby("session", sort=True):
        open_ts = pd.Timestamp(sess).tz_localize(NY) + pd.Timedelta(hours=9, minutes=30)
        groups[sess] = SessionTape(g, int(open_ts.tz_convert("UTC").value))
    all_sessions = np.array(sorted(groups.keys()))
    print(f"  {len(tape):,} prints, {len(all_sessions)} sessions", flush=True)

    # validate the cache HERE too, at the consumer. Codex: the fingerprint
    # guard lived in script 18 only, so this script could happily read a stale
    # decision table built by older feature code.
    stamp = DEC.with_suffix(".fingerprint")
    if not stamp.exists():
        raise SystemExit(f"{DEC.name} has no fingerprint; rerun "
                         "18_absorption_drive.py to rebuild it")
    print(f"decision table fingerprint {stamp.read_text(encoding='utf-8').strip()}",
          flush=True)

    dec_full = pd.read_parquet(DEC)
    sessions = np.array(sorted(dec_full["session"].unique()))
    is_set = set(sessions[:IS_SESSIONS])
    is_full = dec_full["session"].isin(is_set).to_numpy()

    # Thresholds are frozen on the FULL IS population, exactly as script 18
    # froze them. Computing them after truncating the grid for the horizon
    # changed them (|imb| 0.283957 vs 0.285714, volume 818 vs 805), so the
    # policy under test was not the one the markout study froze. Codex caught
    # this; it is IS-only either way, so it was never leakage, but it was a
    # different rule than advertised.
    tail_cut = float(np.quantile(np.abs(dec_full.loc[is_full, "imb"].to_numpy()), TAIL_Q))
    vol_hi = float(np.quantile(dec_full.loc[is_full, "vol"].to_numpy(), 0.90))
    disp_lo = float(np.quantile(dec_full.loc[is_full, "abs_disp"].to_numpy(), 0.25))
    disp_hi = float(np.quantile(dec_full.loc[is_full, "abs_disp"].to_numpy(), 0.75))

    # only now truncate, so that delay + horizon fits inside the tape
    dec = dec_full[dec_full["tau_s"] <= LAST_TAU_S].reset_index(drop=True)
    dec["sample"] = np.where(dec["session"].isin(is_set), "IS", "OOS")

    print(f"decisions in range: {len(dec):,} (tau <= {LAST_TAU_S:.0f}s so that "
          f"delay+horizon fits inside 10:30)", flush=True)
    print(f"frozen on IS: |imb| >= {tail_cut:.4f}; vol binds at >= "
          f"{int(np.ceil(vol_hi))}; |disp| <= {disp_lo:.0f} / >= {disp_hi:.0f}",
          flush=True)
    print(f"frozen policy: entry at first print >= tau+{ENTRY_DELAY_S}s, "
          f"horizon {HORIZON_S}s, fill at the crossing print, "
          f"one position at a time", flush=True)

    dom = np.sign(dec["imb"].to_numpy())
    hi_vol = dec["vol"].to_numpy() >= vol_hi
    families = {
        "imb_tail":   (np.abs(dec["imb"].to_numpy()) >= tail_cut, dom),
        "absorption": (hi_vol & (dec["abs_disp"].to_numpy() <= disp_lo), -dom),
        "drive":      (hi_vol & (dec["abs_disp"].to_numpy() >= disp_hi), dom),
    }

    m_cells = len(families) * len(BRACKETS)
    adj = 1.0 - 0.05 / m_cells
    print(f"cells = {m_cells}; reporting a {adj:.4%} interval "
          f"(Bonferroni-adjusted, actually applied) beside the 95%",
          flush=True)

    rng = np.random.default_rng(SEED)
    rows = []
    per_sess_rows = []

    cells = [(f, b) for f in families for b in BRACKETS]
    for fam, (sl, tp) in track(cells, label="barrier cells"):
        mask, direction = families[fam]
        res = run_family(groups, dec, mask, direction, sl, tp)
        took = res[res["taken"]].copy()
        if len(took) < 30:
            continue

        for sample in ("IS", "OOS", "ALL"):
            if sample == "ALL":
                t = took
            else:
                keep = (took["session"].isin(is_set) if sample == "IS"
                        else ~took["session"].isin(is_set))
                t = took[keep]
            if len(t) < 30:
                continue

            gross = t["ticks"].to_numpy()
            # per-session sums/counts over ALL sessions, zero-signal included
            sess_list = (all_sessions if sample == "ALL"
                         else np.array(sorted(is_set)) if sample == "IS"
                         else np.array([s for s in all_sessions if s not in is_set]))
            g_by = t.groupby("session")["ticks"].agg(["sum", "count"])
            sums = np.array([float(g_by["sum"].get(s, 0.0)) for s in sess_list])
            cnts = np.array([float(g_by["count"].get(s, 0)) for s in sess_list])

            for c in COSTS:
                net = gross - c
                net_sums = sums - c * cnts
                ci = boot_mean_ci(net_sums, cnts, rng, (0.95, adj))
                longs = t[t["d"] > 0]["ticks"].to_numpy() - c
                shorts = t[t["d"] < 0]["ticks"].to_numpy() - c
                rows.append(dict(
                    family=fam, sl=sl, tp=tp, sample=sample, cost=c,
                    n=len(t), n_sessions=int((cnts > 0).sum()),
                    trades_per_active_session=float(cnts[cnts > 0].mean()),
                    wr=float((gross > 0).mean()),
                    gross_ev=float(gross.mean()), net_ev=float(net.mean()),
                    lo95=ci[0.95][0], hi95=ci[0.95][1],
                    lo_adj=ci[adj][0], hi_adj=ci[adj][1],
                    long_n=len(longs), long_ev=float(longs.mean()) if len(longs) else np.nan,
                    short_n=len(shorts), short_ev=float(shorts.mean()) if len(shorts) else np.nan,
                    long_share=float(len(longs) / len(t)),
                    # Codex corrected my algebra here. With
                    #   E[L] = a + b - c   and   E[S] = a - b - c
                    # where a is the directional signal contribution, b the
                    # common drift and c the cost, then
                    #   (L + S)/2 = a - c   <- direction-BALANCED, drift removed
                    #   (L - S)/2 = b       <- the DRIFT itself
                    # My earlier "drift_neutral" column reported (L-S)/2, which
                    # isolates drift instead of cancelling it. Both are kept
                    # now, each under its correct name.
                    dir_balanced=float((longs.mean() + shorts.mean()) / 2.0)
                    if len(longs) and len(shorts) else np.nan,
                    drift_estimate=float((longs.mean() - shorts.mean()) / 2.0)
                    if len(longs) and len(shorts) else np.nan,
                    pct_timeout=float((t["kind"] == "timeout").mean()),
                    n_timeout=int((t["kind"] == "timeout").sum()),
                    # count skips for THIS sample, not the whole run. The old
                    # version stamped the all-sample total onto every row.
                    skipped_busy=int(((res["kind"] == "skipped_busy")
                                      & (res["session"].isin(is_set) if sample == "IS"
                                         else ~res["session"].isin(is_set) if sample == "OOS"
                                         else True)).sum()),
                ))
        per_sess_rows.append(res.assign(family=fam, sl=sl, tp=tp))

    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    pd.concat(per_sess_rows, ignore_index=True).to_csv(OUT_SESS, index=False)

    # ------------------------------ report -------------------------------
    print("", flush=True)
    print("=" * 112, flush=True)
    print("PRIMER PASO con barreras. Resultado primario = EV NETO en ticks, "
          "incertidumbre a nivel sesion.", flush=True)
    print("Sin test binomial: los payouts son variables (overshoot en el print "
          "que cruza, timeout a mercado).", flush=True)
    print("", flush=True)

    base = out[out["cost"].eq(1.8)]
    for fam in families:
        print(f"--- {fam}, costo 1.8 (optimista) ---", flush=True)
        print("| SL/TP | muestra | n | trades/ses | WR | EV bruto | EV neto | "
              f"IC95 | IC{adj:.2%} | longs | shorts | mix long | "
              "balanceado dir | deriva | n timeout |",
              flush=True)
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|", flush=True)
        s = base[base["family"].eq(fam)].sort_values(["sl", "sample"])
        for r in s.itertuples():
            print(f"| {r.sl}/{r.tp} | {r.sample} | {r.n:,} | "
                  f"{r.trades_per_active_session:.1f} | {r.wr:.1%} | "
                  f"{r.gross_ev:+.2f} | **{r.net_ev:+.2f}** | "
                  f"[{r.lo95:+.2f}, {r.hi95:+.2f}] | "
                  f"[{r.lo_adj:+.2f}, {r.hi_adj:+.2f}] | "
                  f"{r.long_ev:+.2f} | {r.short_ev:+.2f} | "
                  f"{r.long_share:.0%} | {r.dir_balanced:+.2f} | "
                  f"{r.drift_estimate:+.2f} | {r.n_timeout} |", flush=True)
        print("", flush=True)

    print("VEREDICTO: ninguna celda avanza salvo que su cota inferior "
          f"AJUSTADA supere {ADVANCE_BAR} ticks netos", flush=True)
    print("", flush=True)
    any_pass = False
    for c in COSTS:
        sub = out[out["cost"].eq(c) & out["sample"].eq("OOS")]
        if not len(sub):
            continue
        best = sub.loc[sub["lo_adj"].idxmax()]
        ok = bool(best["lo_adj"] > ADVANCE_BAR)
        any_pass |= ok
        print(f"  costo {c}: mejor cota inferior ajustada OOS = "
              f"{best['lo_adj']:+.3f} ticks "
              f"({best['family']} {int(best['sl'])}/{int(best['tp'])}) "
              f"-> {'AVANZA' if ok else 'NO avanza'}", flush=True)
        # Codex: the LOWER bound answers "does anything advance". A NEGATIVE
        # conclusion needs the UPPER bounds, and a cell whose upper bound sits
        # above the bar is inconclusive, not refuted.
        incon = sub[sub["hi_adj"] > ADVANCE_BAR]
        print(f"      celdas OOS cuya cota SUPERIOR excluye {ADVANCE_BAR}: "
              f"{len(sub) - len(incon)} de {len(sub)}", flush=True)
        for r in incon.itertuples():
            print(f"      INCONCLUSA: {r.family} {int(r.sl)}/{int(r.tp)} "
                  f"neto {r.net_ev:+.3f}, ajustado "
                  f"[{r.lo_adj:+.3f}, {r.hi_adj:+.3f}]", flush=True)
        sub_all = out[out["cost"].eq(c) & out["sample"].eq("ALL")]
        if len(sub_all):
            print(f"      pooled: cota superior ajustada maxima = "
                  f"{sub_all['hi_adj'].max():+.3f} "
                  f"({'todas excluyen' if sub_all['hi_adj'].max() <= ADVANCE_BAR else 'alguna NO excluye'} "
                  f"{ADVANCE_BAR})", flush=True)
    print("", flush=True)
    print(f"  CONCLUSION: {'hay celda que avanza' if any_pass else 'NINGUNA celda avanza'}",
          flush=True)
    print("", flush=True)
    print(f"wrote {OUT}", flush=True)
    print(f"wrote {OUT_SESS}", flush=True)


if __name__ == "__main__":
    main()
