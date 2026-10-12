"""Conditional markout study on the aggressor tape — the measurement Codex
proposed in place of my slope/sign gate, after refuting that design.

The question
------------
Does aggressor imbalance predict enough SUBSEQUENT movement to pay a round
trip? Not "is a slope non-zero", but "how many ticks does the selected side
actually capture, and what is the largest round-trip cost that could pay for".

Why this shape and not a regression slope
-----------------------------------------
Codex's objections to the first design, all accepted:

1. A binomial win-rate test against (K+c)/2K is invalid here, because the
   outcome engine produces VARIABLE payouts (overshoot on the crossing print,
   mark-to-market timeouts). Winning 60% at +8 while losing 40% at -16 is
   -1.6 ticks gross and still "beats 50%". So the primary outcome is mean net
   TICKS with session-level uncertainty, never a win rate.
2. Starting the forward target at the last print inside the feature window is
   exactly where the bid-ask bounce artifact enters. With X = q (the terminal
   print sign) and a one-tick spread, the population slope is -0.5 ticks per
   unit imbalance with NO economic signal -- which happened to land right on
   the 0.5 threshold the first design was going to use to pick a rule family.
   Hence the DELAY grid below: a real effect survives a delay, an endpoint
   artifact does not.
3. A regression coefficient in ticks per unit of a [-1, 1] feature is not
   profit per trade. The reported effect here is in ticks per decision.

The null is exactly zero, by symmetry
-------------------------------------
There are no barriers in a markout, so the opposite side's outcome at the same
timestamps is the exact negative of the selected side's. Therefore
mean(signed markout) has null exactly 0 by construction -- no Monte Carlo and
no asymmetry to hide behind. This is the clean version of what the first design
tried to get from a symmetric bracket, and unlike that one it survives
Codex's critique because nothing here depends on execution convention.

Chronological hygiene
---------------------
The tail cutoff and the direction rule are frozen on the FIRST 100 sessions and
then applied unchanged to the LAST 50. Codex's point stands: choosing the sign
or the family after looking at all 150 sessions is outcome-based selection even
if the thresholds are IS-only, so the whole procedure is fixed on IS.

2026 has already been inspected many times, so even the OOS half is NOT virgin.
Everything here is exploratory and is labelled as such.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATA, NY  # noqa: E402
from progress import track  # noqa: E402

TAPE = DATA / "tape" / "tape_trades_2026.parquet"
OUT = DATA / "reports" / "markout_study.csv"
OUT_STRAT = DATA / "reports" / "markout_by_terminal_sign.csv"

# All tape primitives and the frozen study constants now live in tape_lib,
# so scripts 17 and 18 cannot drift apart. Moved verbatim.
from tape_lib import (  # noqa: E402
    NS, GRID_S, FEAT_S, DELAYS_S, HORIZONS_S, REFS,
    WIN_FROM_S, WIN_TO_S, IS_SESSIONS, TAIL_Q, N_BOOT, SEED, COSTS,
    SessionTape,
)


def build_decisions(tape: pd.DataFrame) -> pd.DataFrame:
    """One row per (session, decision instant), with the feature and every
    (ref, delay, horizon) markout already attached."""
    rows: list[pd.DataFrame] = []
    max_tail = max(DELAYS_S) + max(HORIZONS_S)

    # groupby once: masking 13M rows per session would be 150 full scans
    groups = list(tape.groupby("session", sort=True))

    for sess, g in track(groups, label="markout decisions"):
        if len(g) < 1000:
            continue
        # 09:30:00 ET of this session, in UTC ns
        open_ts = pd.Timestamp(sess).tz_localize(NY) + pd.Timedelta(hours=9, minutes=30)
        open_ns = int(open_ts.tz_convert("UTC").value)

        st = SessionTape(g, open_ns)

        # decision instants: need FEAT_S of history and the full tail available
        k0 = int(np.ceil(FEAT_S / GRID_S))
        last_ok = WIN_TO_S - max_tail
        ks = np.arange(k0, int(np.floor(last_ok / GRID_S)) + 1)
        if len(ks) == 0:
            continue
        tau_s = ks * float(GRID_S)
        tau_ns = open_ns + (tau_s * NS).astype("int64")

        imb, tot = st.imbalance(tau_ns - int(FEAT_S * NS), tau_ns)
        qterm = st.terminal_sign(tau_ns)

        d = pd.DataFrame({
            "session": sess,
            "tau_s": tau_s,
            "imb": imb,
            "vol": tot,
            "q_term": qterm,
        })

        for ref in REFS:
            for dl in DELAYS_S:
                e_ns = tau_ns + int(dl * NS)
                ei = st.idx_at(e_ns)
                p_entry = st.price(ei, ref)
                for h in HORIZONS_S:
                    x_ns = e_ns + int(h * NS)
                    xi = st.idx_at(x_ns)
                    p_exit = st.price(xi, ref)
                    d[f"mk_{ref}_{dl}_{h}"] = p_exit - p_entry

        rows.append(d)

    out = pd.concat(rows, ignore_index=True)
    return out[out["imb"].notna()].reset_index(drop=True)


def boot_mean(vals: np.ndarray, keys: np.ndarray, rng: np.random.Generator,
              n_boot: int = N_BOOT) -> tuple[float, float]:
    """Session-level block bootstrap of a mean. Sessions are the unit."""
    uniq = np.unique(keys)
    idx_by_key = {k: np.flatnonzero(keys == k) for k in uniq}
    out = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by_key[k] for k in pick])
        out[i] = vals[idx].mean()
    return float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))


def main() -> None:
    print("loading tape...", flush=True)
    tape = pd.read_parquet(TAPE)
    ny = pd.to_datetime(tape["ts_ns"], utc=True).dt.tz_convert(NY)
    secs = (ny.dt.hour * 3600 + ny.dt.minute * 60 + ny.dt.second
            + ny.dt.microsecond / 1e6) - 9.5 * 3600
    tape = tape[(secs >= WIN_FROM_S) & (secs < WIN_TO_S)].reset_index(drop=True)
    print(f"  {len(tape):,} prints, {tape['session'].nunique()} sessions, "
          f"09:30-10:30 ET", flush=True)

    dec = build_decisions(tape)
    sessions = np.array(sorted(dec["session"].unique()))
    is_set = set(sessions[:IS_SESSIONS])
    oos_set = set(sessions[IS_SESSIONS:])
    dec["sample"] = np.where(dec["session"].isin(is_set), "IS", "OOS")

    print("", flush=True)
    print(f"decisions: {len(dec):,} on a {GRID_S}s grid, "
          f"{len(sessions)} sessions "
          f"(IS {len(is_set)} / OOS {len(oos_set)})", flush=True)

    # ---- freeze the selection rule on IS ONLY ---------------------------
    is_mask = dec["sample"].eq("IS").to_numpy()
    tail_cut = float(np.quantile(np.abs(dec.loc[is_mask, "imb"].to_numpy()), TAIL_Q))
    print(f"frozen on IS: |imb| tail cutoff at q{TAIL_Q:.2f} = {tail_cut:.4f}",
          flush=True)
    print("direction rule, frozen: d = sign(imb). Nothing else is fitted.",
          flush=True)

    dec["selected"] = np.abs(dec["imb"]) >= tail_cut
    dec["d"] = np.sign(dec["imb"]).astype("int64")

    rng = np.random.default_rng(SEED)
    rows: list[dict] = []

    cells = [(ref, dl, h) for ref in REFS for dl in DELAYS_S for h in HORIZONS_S]
    for ref, dl, h in track(cells, label="markout cells"):
        col = f"mk_{ref}_{dl}_{h}"
        for sample in ("IS", "OOS"):
            for group, gmask in (("tail", dec["selected"]), ("all", pd.Series(True, index=dec.index))):
                m = dec["sample"].eq(sample) & gmask & dec[col].notna() & dec["d"].ne(0)
                sub = dec[m]
                if len(sub) < 50:
                    continue
                signed = (sub["d"].to_numpy() * sub[col].to_numpy())
                keys = sub["session"].to_numpy()
                mu = float(signed.mean())
                lo, hi = boot_mean(signed, keys, rng)
                rows.append(dict(
                    ref=ref, delay_s=dl, horizon_s=h, sample=sample, group=group,
                    n=len(sub), n_sessions=sub["session"].nunique(),
                    markout_ticks=mu, lo95=lo, hi95=hi,
                    sd=float(signed.std()),
                    max_cost_payable=lo,     # the honest ceiling: lower bound
                ))

    res = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT, index=False)

    # ---- terminal-sign stratification (the bounce diagnostic) -----------
    strat_rows: list[dict] = []
    for ref in REFS:
        for dl in DELAYS_S:
            col = f"mk_{ref}_{dl}_{HORIZONS_S[0]}"
            for q in (-1, 1):
                m = (dec["selected"] & dec["q_term"].eq(q)
                     & dec[col].notna() & dec["d"].ne(0))
                sub = dec[m]
                if len(sub) < 50:
                    continue
                signed = sub["d"].to_numpy() * sub[col].to_numpy()
                strat_rows.append(dict(
                    ref=ref, delay_s=dl, horizon_s=HORIZONS_S[0], q_term=q,
                    n=len(sub), markout_ticks=float(signed.mean())))
    pd.DataFrame(strat_rows).to_csv(OUT_STRAT, index=False)

    # ---------------------------- report ---------------------------------
    n_cells = len(cells) * 2   # tail and all
    print("", flush=True)
    print("=" * 86, flush=True)
    print("MARKOUT de la cola de desbalance, en TICKS por decision", flush=True)
    print("null exacto = 0 por simetria (el lado opuesto es el negativo exacto)",
          flush=True)
    print(f"celdas corridas = {n_cells}, Bonferroni p < {0.05 / n_cells:.5f}",
          flush=True)
    print("", flush=True)

    for sample in ("IS", "OOS"):
        print(f"--- {sample} ---", flush=True)
        print("| ref | delay | horiz | grupo | n | markout ticks | IC95 | "
              "¿IC excluye 0? | ¿paga 1.8? |", flush=True)
        print("|---|---|---|---|---|---|---|---|---|", flush=True)
        sub = res[res["sample"].eq(sample)].sort_values(
            ["group", "ref", "delay_s", "horizon_s"])
        for r in sub.itertuples():
            excl = "SI" if (r.lo95 > 0 or r.hi95 < 0) else "no"
            pays = "SI" if r.lo95 >= 1.8 else "no"
            print(f"| {r.ref} | {r.delay_s}s | {r.horizon_s}s | {r.group} | "
                  f"{r.n:,} | {r.markout_ticks:+.4f} | "
                  f"[{r.lo95:+.4f}, {r.hi95:+.4f}] | {excl} | {pays} |", flush=True)
        print("", flush=True)

    print("DIAGNOSTICO DE BOUNCE: markout por signo del print terminal", flush=True)
    print("(si el efecto se invierte con q_term, es artefacto de endpoint)",
          flush=True)
    print("", flush=True)
    print("| ref | delay | q_term | n | markout ticks |", flush=True)
    print("|---|---|---|---|---|", flush=True)
    for r in pd.DataFrame(strat_rows).itertuples():
        print(f"| {r.ref} | {r.delay_s}s | {r.q_term:+d} | {r.n:,} | "
              f"{r.markout_ticks:+.4f} |", flush=True)

    print("", flush=True)
    print("MAXIMO COSTO DE IDA Y VUELTA QUE EL EFECTO PODRIA PAGAR", flush=True)
    print("(cota inferior del IC95 del markout, grupo cola, OOS)", flush=True)
    print("", flush=True)
    best = res[res["sample"].eq("OOS") & res["group"].eq("tail")]
    if len(best):
        b = best.loc[best["lo95"].idxmax()]
        print(f"  mejor celda OOS: ref={b['ref']} delay={b['delay_s']}s "
              f"horiz={b['horizon_s']}s", flush=True)
        print(f"  markout {b['markout_ticks']:+.4f} ticks, "
              f"cota inferior {b['lo95']:+.4f}", flush=True)
        for c in COSTS:
            print(f"    costo {c} ticks -> "
                  f"{'PAGA' if b['lo95'] >= c else 'NO PAGA'}", flush=True)
    print("", flush=True)
    print(f"wrote {OUT}", flush=True)
    print(f"wrote {OUT_STRAT}", flush=True)


if __name__ == "__main__":
    main()
