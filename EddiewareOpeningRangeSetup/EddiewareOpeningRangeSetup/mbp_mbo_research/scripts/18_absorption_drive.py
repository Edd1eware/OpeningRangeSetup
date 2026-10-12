"""Second family of the tape study: the volume x displacement INTERACTION,
plus session-level robustness on the first family.

Why this family and not another re-signing of the same feature
---------------------------------------------------------------
Script 17 closed the first family: the tail of normalised aggressor imbalance
on a 15s grid does not pay a round trip (IS tail positive, OOS tail negative,
and the pre-registered bounce diagnostic fires). Codex's standing objection to
treating that as a verdict on order flow is specific and correct:

    absorption conditions on HIGH VOLUME AND LITTLE DISPLACEMENT, which
    normalised imbalance alone does not encode. Opposing effects across
    activity or volatility regimes can cancel.

So this is a genuinely different feature -- an interaction, not a sign flip on
the feature that already failed. Two mechanisms, both named in advance:

    absorption : trailing volume >= IS p90  AND  |displacement| <= IS p25
                 direction AGAINST the dominant aggressor.
                 Mechanism: size is being hit into a bigger passive player who
                 is absorbing it, so the aggressor is the one who is wrong.

    drive      : trailing volume >= IS p90  AND  |displacement| >= IS p75
                 direction WITH the dominant aggressor.
                 Mechanism: urgent flow that is actually moving price keeps
                 moving it.

They are deliberate opposites. Running both is not a search: a single feature
cannot be made to pass by picking whichever sign won, because each one's
direction is pinned to its own mechanism in advance and both are reported.

Everything else is unchanged from notes_md/2026-10-12_PREREGISTRO_V2.md: the
same markout machinery, the same (ref x delay x horizon) grid, every threshold
frozen on the FIRST 100 sessions, session-level block bootstrap, and the same
advancement bar (lower CI bound of the OOS markout above 2.8 ticks, with no
inversion by terminal print sign).

Multiple testing, declared and accumulated
------------------------------------------
Family 1 (script 17) already spent 36 cells. This script adds
3 families x 2 refs x 3 delays x 3 horizons = 54 reported cells, of which the
imb_tail ones are a re-report of family 1 for robustness, not new tests.
Accumulated NEW cells across the two scripts: 36 + 36 = 72, so the Bonferroni
threshold quoted below is 0.05 / 72.

Robustness added here, because Codex asked for it specifically
--------------------------------------------------------------
Per-SESSION jackknife: drop one session at a time and report the range of the
mean. Removing the best single TRADE is the weak version of this test; removing
the best and worst SESSION is the one that catches a result carried by one day.
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
    NS, GRID_S, FEAT_S, DELAYS_S, HORIZONS_S, REFS,
    WIN_FROM_S, WIN_TO_S, IS_SESSIONS, TAIL_Q, N_BOOT, SEED, COSTS,
    SessionTape,
)

TAPE = DATA / "tape" / "tape_trades_2026.parquet"
DEC_OUT = DATA / "tape" / "decisions_15s.parquet"
OUT = DATA / "reports" / "absorption_drive.csv"
JACK_OUT = DATA / "reports" / "absorption_drive_jackknife.csv"

ADVANCE_BAR = 2.8      # declared in the pre-registration
STOP_BAR = 1.8         # optimistic cost


def build_decisions(tape: pd.DataFrame) -> pd.DataFrame:
    """One row per (session, decision instant): imbalance, volume, signed
    displacement, terminal print sign, and every (ref, delay, horizon) markout.

    Everything in the feature block is measured over [tau - FEAT_S, tau) and is
    therefore strictly available before tau.
    """
    rows: list[pd.DataFrame] = []
    max_tail = max(DELAYS_S) + max(HORIZONS_S)
    groups = list(tape.groupby("session", sort=True))

    for sess, g in track(groups, label="decisions"):
        if len(g) < 1000:
            continue
        open_ts = pd.Timestamp(sess).tz_localize(NY) + pd.Timedelta(hours=9, minutes=30)
        open_ns = int(open_ts.tz_convert("UTC").value)
        st = SessionTape(g, open_ns)

        k0 = int(np.ceil(FEAT_S / GRID_S))
        last_ok = WIN_TO_S - max_tail
        ks = np.arange(k0, int(np.floor(last_ok / GRID_S)) + 1)
        if len(ks) == 0:
            continue
        tau_s = ks * float(GRID_S)
        tau_ns = open_ns + (tau_s * NS).astype("int64")
        w0_ns = tau_ns - int(FEAT_S * NS)

        imb, tot = st.imbalance(w0_ns, tau_ns)
        qterm = st.terminal_sign(tau_ns)

        # Signed displacement over the feature window, in ticks, same estimator
        # at both ends so nothing is measured against a mixed base.
        # idx_before, NOT idx_at: idx_at returns the first print at or AFTER the
        # instant, which reaches past tau and is lookahead in a feature that
        # decides selection. Codex found this; see tape_lib.idx_before.
        p_start = st.price(st.idx_before(w0_ns), "print")
        p_end = st.price(st.idx_before(tau_ns), "print")
        disp = p_end - p_start

        d = pd.DataFrame({
            "session": sess,
            "tau_s": tau_s,
            "imb": imb,
            "vol": tot,
            "disp": disp,
            "abs_disp": np.abs(disp),
            "q_term": qterm,
        })

        for ref in REFS:
            for dl in DELAYS_S:
                e_ns = tau_ns + int(dl * NS)
                p_entry = st.price(st.idx_at(e_ns), ref)
                for h in HORIZONS_S:
                    p_exit = st.price(st.idx_at(e_ns + int(h * NS)), ref)
                    d[f"mk_{ref}_{dl}_{h}"] = p_exit - p_entry

        rows.append(d)

    out = pd.concat(rows, ignore_index=True)
    keep = out["imb"].notna() & out["abs_disp"].notna() & (out["vol"] > 0)
    return out[keep].reset_index(drop=True)


def boot_mean(vals: np.ndarray, keys: np.ndarray, rng: np.random.Generator,
              n_boot: int = N_BOOT) -> tuple[float, float]:
    """Session-level block bootstrap of a mean. The session is the unit."""
    uniq = np.unique(keys)
    idx_by_key = {k: np.flatnonzero(keys == k) for k in uniq}
    out = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        out[i] = vals[np.concatenate([idx_by_key[k] for k in pick])].mean()
    return float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))


def jackknife_sessions(vals: np.ndarray, keys: np.ndarray) -> dict:
    """Drop one session at a time; report how far the mean can move.
    Catches a result carried by a single day."""
    uniq = np.unique(keys)
    per = np.array([vals[keys == k].sum() for k in uniq])
    cnt = np.array([int((keys == k).sum()) for k in uniq])
    tot, n = per.sum(), cnt.sum()
    means = (tot - per) / np.maximum(n - cnt, 1)
    worst_i, best_i = int(np.argmin(means)), int(np.argmax(means))
    return dict(
        mean_full=float(tot / n),
        jack_min=float(means.min()),
        jack_max=float(means.max()),
        session_dropped_for_min=str(uniq[worst_i]),
        session_dropped_for_max=str(uniq[best_i]),
        n_sessions=len(uniq),
    )


def feature_fingerprint() -> str:
    """Hash of the code that BUILDS the features, so a cached decision table
    can never silently outlive a correction to it.

    Codex: "Cached decisions are reused without provenance validation. A code
    correction can silently leave stale features in decisions_15s.parquet."
    That is exactly what would have happened with the displacement lookahead
    fix, so the cache now carries the fingerprint of its own producer.
    """
    import hashlib
    here = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for name in ("tape_lib.py", "18_absorption_drive.py"):
        h.update((here / name).read_bytes())
    return h.hexdigest()[:16]


def main() -> None:
    fp = feature_fingerprint()
    stamp = DEC_OUT.with_suffix(".fingerprint")
    cached_ok = (DEC_OUT.exists() and stamp.exists()
                 and stamp.read_text(encoding="utf-8").strip() == fp)

    if DEC_OUT.exists() and not cached_ok:
        print(f"REBUILDING: cached {DEC_OUT.name} was produced by different "
              f"feature code (want {fp})", flush=True)

    if cached_ok:
        print(f"reusing decision table {DEC_OUT} (fingerprint {fp})", flush=True)
        dec = pd.read_parquet(DEC_OUT)
    else:
        print("loading tape...", flush=True)
        tape = pd.read_parquet(TAPE)
        ny = pd.to_datetime(tape["ts_ns"], utc=True).dt.tz_convert(NY)
        secs = (ny.dt.hour * 3600 + ny.dt.minute * 60 + ny.dt.second
                + ny.dt.microsecond / 1e6) - 9.5 * 3600
        tape = tape[(secs >= WIN_FROM_S) & (secs < WIN_TO_S)].reset_index(drop=True)
        print(f"  {len(tape):,} prints, {tape['session'].nunique()} sessions",
              flush=True)
        dec = build_decisions(tape)
        DEC_OUT.parent.mkdir(parents=True, exist_ok=True)
        dec.to_parquet(DEC_OUT, index=False)
        stamp.write_text(fp, encoding="utf-8")
        print(f"wrote {DEC_OUT} (fingerprint {fp})", flush=True)

    sessions = np.array(sorted(dec["session"].unique()))
    is_set = set(sessions[:IS_SESSIONS])
    dec["sample"] = np.where(dec["session"].isin(is_set), "IS", "OOS")
    is_mask = dec["sample"].eq("IS").to_numpy()

    # ---- every threshold frozen on IS ONLY ------------------------------
    tail_cut = float(np.quantile(np.abs(dec.loc[is_mask, "imb"].to_numpy()), TAIL_Q))
    vol_hi = float(np.quantile(dec.loc[is_mask, "vol"].to_numpy(), 0.90))
    disp_lo = float(np.quantile(dec.loc[is_mask, "abs_disp"].to_numpy(), 0.25))
    disp_hi = float(np.quantile(dec.loc[is_mask, "abs_disp"].to_numpy(), 0.75))

    print("", flush=True)
    print(f"decisions: {len(dec):,} on a {GRID_S}s grid, {len(sessions)} sessions "
          f"(IS {IS_SESSIONS} / OOS {len(sessions) - IS_SESSIONS})", flush=True)
    print("thresholds FROZEN on the first 100 sessions:", flush=True)
    print(f"  |imb| tail  q{TAIL_Q:.2f} = {tail_cut:.4f}", flush=True)
    # print the threshold as the rule ACTUALLY binds. Codex: the frozen value
    # is 815.1000000000022, so integer volume must be >= 816, and a report of
    # "815" does not reproduce the implemented rule.
    print(f"  volume high q0.90       = {vol_hi:.4f} -> binds at >= "
          f"{int(np.ceil(vol_hi))} contracts / 15s", flush=True)
    print(f"  |disp| low  q0.25       = {disp_lo:.1f} ticks", flush=True)
    print(f"  |disp| high q0.75       = {disp_hi:.1f} ticks", flush=True)

    dom = np.sign(dec["imb"].to_numpy())          # dominant aggressor side
    hi_vol = dec["vol"].to_numpy() >= vol_hi
    lo_disp = dec["abs_disp"].to_numpy() <= disp_lo
    up_disp = dec["abs_disp"].to_numpy() >= disp_hi

    families = {
        # name            selection mask                        direction
        "imb_tail":   (np.abs(dec["imb"].to_numpy()) >= tail_cut, dom),
        "absorption": (hi_vol & lo_disp,                        -dom),
        "drive":      (hi_vol & up_disp,                          dom),
    }

    for name, (mask, _) in families.items():
        n_is = int((mask & is_mask).sum())
        n_oos = int((mask & ~is_mask).sum())
        print(f"  family {name:<11} fires on {mask.sum():,} decisions "
              f"({mask.mean():.2%})  IS {n_is:,} / OOS {n_oos:,}", flush=True)

    rng = np.random.default_rng(SEED)
    rows: list[dict] = []
    jacks: list[dict] = []

    cells = [(fam, ref, dl, h) for fam in families for ref in REFS
             for dl in DELAYS_S for h in HORIZONS_S]
    for fam, ref, dl, h in track(cells, label="markout cells"):
        mask, direction = families[fam]
        col = f"mk_{ref}_{dl}_{h}"
        for sample in ("IS", "OOS"):
            m = (mask & dec["sample"].eq(sample).to_numpy()
                 & dec[col].notna().to_numpy() & (direction != 0))
            if m.sum() < 50:
                continue
            signed = direction[m] * dec[col].to_numpy()[m]
            keys = dec["session"].to_numpy()[m]
            lo, hi = boot_mean(signed, keys, rng)
            rows.append(dict(
                family=fam, ref=ref, delay_s=dl, horizon_s=h, sample=sample,
                n=int(m.sum()), n_sessions=len(np.unique(keys)),
                markout_ticks=float(signed.mean()), lo95=lo, hi95=hi,
                sd=float(signed.std()),
            ))
            if dl == 0.5 and h == 15:    # jackknife the primary cell only
                j = jackknife_sessions(signed, keys)
                j.update(family=fam, ref=ref, sample=sample)
                jacks.append(j)

    res = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT, index=False)
    jk = pd.DataFrame(jacks)
    jk.to_csv(JACK_OUT, index=False)

    n_new_cells = 72
    print("", flush=True)
    print("=" * 92, flush=True)
    print("MARKOUT por familia, en TICKS por decision. "
          "null exacto = 0 por simetria.", flush=True)
    print(f"celdas NUEVAS acumuladas (scripts 17+18) = {n_new_cells}, "
          f"Bonferroni p < {0.05 / n_new_cells:.5f}", flush=True)
    print(f"barra de AVANCE declarada: cota inferior IC95 del OOS > "
          f"{ADVANCE_BAR} ticks", flush=True)
    print("", flush=True)

    for fam in families:
        print(f"--- familia {fam} ---", flush=True)
        print("| ref | delay | horiz | muestra | n | markout | IC95 | "
              "IC excl 0 | pasa avance |", flush=True)
        print("|---|---|---|---|---|---|---|---|---|", flush=True)
        sub = res[res["family"].eq(fam)].sort_values(
            ["sample", "ref", "delay_s", "horizon_s"])
        for r in sub.itertuples():
            excl = "SI" if (r.lo95 > 0 or r.hi95 < 0) else "no"
            adv = "SI" if (r.sample == "OOS" and r.lo95 > ADVANCE_BAR) else "no"
            print(f"| {r.ref} | {r.delay_s}s | {r.horizon_s}s | {r.sample} | "
                  f"{r.n:,} | {r.markout_ticks:+.4f} | "
                  f"[{r.lo95:+.4f}, {r.hi95:+.4f}] | {excl} | {adv} |", flush=True)
        print("", flush=True)

    print("JACKKNIFE POR SESION (celda primaria delay=0.5s horiz=15s)", flush=True)
    print("rango del markout medio al quitar UNA sesion", flush=True)
    print("", flush=True)
    print("| familia | ref | muestra | n ses | medio | min jack | max jack | "
          "¿cambia de signo? |", flush=True)
    print("|---|---|---|---|---|---|---|---|", flush=True)
    for r in jk.itertuples():
        flips = "SI" if (r.mean_full > 0) != (r.jack_min > 0) or \
                        (r.mean_full > 0) != (r.jack_max > 0) else "no"
        print(f"| {r.family} | {r.ref} | {r.sample} | {r.n_sessions} | "
              f"{r.mean_full:+.4f} | {r.jack_min:+.4f} | {r.jack_max:+.4f} | "
              f"{flips} |", flush=True)

    print("", flush=True)
    print("VEREDICTO CONTRA LAS BARRAS DECLARADAS", flush=True)
    oos = res[res["sample"].eq("OOS")]
    any_adv = False
    for fam in families:
        s = oos[oos["family"].eq(fam)]
        if not len(s):
            continue
        best = s.loc[s["lo95"].idxmax()]
        passes = bool(best["lo95"] > ADVANCE_BAR)
        any_adv |= passes
        print(f"  {fam:<11} mejor cota inferior OOS = {best['lo95']:+.4f} ticks "
              f"(ref={best['ref']} d={best['delay_s']}s h={best['horizon_s']}s) "
              f"-> {'AVANZA' if passes else 'NO avanza'}", flush=True)
        for c in COSTS:
            print(f"      vs costo {c}: "
                  f"{'paga' if best['lo95'] >= c else 'NO paga'}", flush=True)
    print("", flush=True)
    print(f"  CONCLUSION: {'alguna familia avanza' if any_adv else 'NINGUNA familia supera la barra de avance'}",
          flush=True)
    print("", flush=True)
    print(f"wrote {OUT}", flush=True)
    print(f"wrote {JACK_OUT}", flush=True)


if __name__ == "__main__":
    main()
