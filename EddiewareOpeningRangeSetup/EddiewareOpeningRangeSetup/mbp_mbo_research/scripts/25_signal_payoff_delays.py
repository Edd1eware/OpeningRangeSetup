"""Signal payoff with NO occupancy filter, across a grid of declared delays.

Closes the last two estimands on Codex's round-4 list of what the project had
not measured.

Estimand 5: other pre-declared delays
-------------------------------------
Everything so far used a single 0.5s entry delay in the barrier engines (and
0 / 0.5 / 2s in the markout). A delay grid is diagnostic, not a search: a
signal with genuine short-lived content decays as the delay grows, while an
endpoint or microstructure artifact dies immediately. Reporting the whole grid
makes the shape visible instead of picking the best cell.

Estimand 6: payoff per signal, independent of occupancy
-------------------------------------------------------
Codex: "You also have not estimated the payoff of every candidate signal
independently of bracket-specific occupancy."

Script 24 attacked that with a common fixed slot, but occupancy still threw away
1,908 of 2,817 imb_tail decisions. Here the occupancy filter is REMOVED
entirely: every selected decision gets a trade, so the signal set is identical
across every delay and bracket, and nothing is discarded.

That is only legitimate because the uncertainty is a SESSION-level cluster
bootstrap. The session is the resampling unit, so overlapping trades inside a
session do not break the inference -- their dependence is preserved by
resampling whole sessions. This is the same reason the earlier bootstraps were
valid, and it is what makes the no-occupancy version measurable at all.

WHAT THIS IS NOT
----------------
Removing occupancy means these are NOT an implementable portfolio: overlapping
positions would need many contracts at once, and the Lucid drawdown is computed
on one account. This measures the SIGNAL's payoff, which is the question Codex
posed, and it must not be read as a tradable equity curve.

Because it keeps every decision, this is the HIGHEST-POWER test of these three
signals in the project. If an edge of the required size existed in them, this is
where it would be least able to hide.

Statistics: primary outcome NET ticks, session cluster bootstrap, 50,000
replicates, m = 3 families x 5 delays x 2 brackets = 30 cells and the reported
interval IS the (1 - 0.05/30) one. No binomial tests.
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
OUT = DATA / "reports" / "signal_payoff_delays.csv"

DELAYS_S = (0.0, 0.5, 2.0, 5.0, 15.0)
BRACKETS = (12, 20)
HORIZON_S = 300
COSTS = (1.8, 2.8, 3.8)
N_BOOT = 50_000
SEED = 20261012
ADVANCE_BAR = 2.5


def walk_sym(px: np.ndarray, ts: np.ndarray, i: int, d: int, k: int,
             t_limit_ns: int) -> tuple[float, str]:
    e = px[i]
    j_end = int(np.searchsorted(ts, t_limit_ns, side="right"))
    if j_end <= i + 1:
        return 0.0, "no_path"
    fav = d * (px[i + 1:j_end] - e)
    hit = (fav >= k) | (fav <= -k)
    if not hit.any():
        return float(fav[-1]), "timeout"
    return float(fav[int(np.argmax(hit))]), "barrier"


def boot_ci(sums: np.ndarray, cnts: np.ndarray, rng: np.random.Generator,
            levels: tuple[float, ...]) -> dict:
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
        op = pd.Timestamp(sess).tz_localize(NY) + pd.Timedelta(hours=9, minutes=30)
        groups[sess] = SessionTape(g, int(op.tz_convert("UTC").value))
    all_sessions = np.array(sorted(groups.keys()))

    stamp = DEC.with_suffix(".fingerprint")
    if not stamp.exists():
        raise SystemExit("decision table has no fingerprint; rerun script 18")
    print(f"decision table fingerprint {stamp.read_text(encoding='utf-8').strip()}",
          flush=True)

    dec = pd.read_parquet(DEC)
    sessions = np.array(sorted(dec["session"].unique()))
    is_set = set(sessions[:IS_SESSIONS])
    is_full = dec["session"].isin(is_set).to_numpy()

    tail_cut = float(np.quantile(np.abs(dec.loc[is_full, "imb"].to_numpy()), TAIL_Q))
    vol_hi = float(np.quantile(dec.loc[is_full, "vol"].to_numpy(), 0.90))
    disp_lo = float(np.quantile(dec.loc[is_full, "abs_disp"].to_numpy(), 0.25))
    disp_hi = float(np.quantile(dec.loc[is_full, "abs_disp"].to_numpy(), 0.75))

    dom = np.sign(dec["imb"].to_numpy())
    hv = dec["vol"].to_numpy() >= vol_hi
    families = {
        "imb_tail":   (np.abs(dec["imb"].to_numpy()) >= tail_cut, dom),
        "absorption": (hv & (dec["abs_disp"].to_numpy() <= disp_lo), -dom),
        "drive":      (hv & (dec["abs_disp"].to_numpy() >= disp_hi), dom),
    }

    # the grid must leave room for the LARGEST delay plus the horizon
    last_tau = WIN_TO_S - HORIZON_S - max(DELAYS_S) - 1.0
    print(f"tau <= {last_tau:.0f}s so the largest delay "
          f"({max(DELAYS_S)}s) + horizon fits inside 10:30", flush=True)
    print("NO occupancy filter: every selected decision is a trade, so the "
          "signal set is identical across delays and brackets.", flush=True)
    print("Valid because the bootstrap resamples SESSIONS, which preserves the "
          "dependence between overlapping trades.", flush=True)
    print("NOT an implementable portfolio: overlapping positions would need "
          "many contracts at once.", flush=True)

    m_cells = len(families) * len(DELAYS_S) * len(BRACKETS)
    adj = 1.0 - 0.05 / m_cells
    print(f"cells = {m_cells}; reporting the {adj:.4%} interval (applied)",
          flush=True)

    rng = np.random.default_rng(SEED)
    rows = []
    cells = [(f, d, k) for f in families for d in DELAYS_S for k in BRACKETS]

    for fam, delay, k in track(cells, label="signal payoff"):
        mask, direction = families[fam]
        sel = mask & (direction != 0) & (dec["tau_s"].to_numpy() <= last_tau)
        sub = dec[sel]
        dirs = direction[sel]
        if len(sub) < 30:
            continue

        recs = []
        for (sess, tau_s), d in zip(zip(sub["session"], sub["tau_s"]), dirs):
            st = groups.get(sess)
            if st is None:
                continue
            e_ns = st.open_ns + int(tau_s * NS) + int(delay * NS)
            i = int(np.searchsorted(st.ts, e_ns, side="left"))
            if i >= len(st.ts):
                continue
            t_limit = st.ts[i] + int(HORIZON_S * NS)
            if t_limit > st.open_ns + int(WIN_TO_S * NS):
                continue
            gross, kind = walk_sym(st.px, st.ts, i, int(d), k, t_limit)
            if kind == "no_path":
                continue
            recs.append((sess, gross, int(d), kind))

        if len(recs) < 30:
            continue
        rec = pd.DataFrame(recs, columns=["session", "ticks", "d", "kind"])

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
                lo_leg = t[t["d"] > 0]["ticks"].to_numpy() - c
                sh_leg = t[t["d"] < 0]["ticks"].to_numpy() - c
                rows.append(dict(
                    family=fam, delay_s=delay, bracket=k, sample=sample, cost=c,
                    n=len(t), n_sessions=int((cnts > 0).sum()),
                    wr=float((gross > 0).mean()),
                    gross_ev=float(gross.mean()), net_ev=float(gross.mean() - c),
                    lo95=ci[0.95][0], hi95=ci[0.95][1],
                    lo_adj=ci[adj][0], hi_adj=ci[adj][1],
                    dir_balanced=float((lo_leg.mean() + sh_leg.mean()) / 2)
                    if len(lo_leg) and len(sh_leg) else np.nan,
                    n_timeout=int((t["kind"] == "timeout").sum()),
                ))

    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    print("", flush=True)
    print("=" * 112, flush=True)
    print("PAYOFF DE LA SENAL sin filtro de ocupacion. Rejilla de demoras.",
          flush=True)
    print("Es el test de MAYOR PODER del proyecto: conserva todas las decisiones.",
          flush=True)
    print("", flush=True)

    base = out[out["cost"].eq(1.8)]
    for fam in families:
        for k in BRACKETS:
            s = base[base["family"].eq(fam) & base["bracket"].eq(k)]
            if not len(s):
                continue
            print(f"--- {fam}, bracket {k}/{k}, costo 1.8 ---", flush=True)
            print("| demora | muestra | n | WR | EV bruto | EV neto | IC95 | "
                  f"IC{adj:.2%} | balanceado dir |", flush=True)
            print("|---|---|---|---|---|---|---|---|---|", flush=True)
            for r in s.sort_values(["delay_s", "sample"]).itertuples():
                print(f"| {r.delay_s}s | {r.sample} | {r.n:,} | {r.wr:.1%} | "
                      f"{r.gross_ev:+.3f} | **{r.net_ev:+.2f}** | "
                      f"[{r.lo95:+.2f}, {r.hi95:+.2f}] | "
                      f"[{r.lo_adj:+.2f}, {r.hi_adj:+.2f}] | "
                      f"{r.dir_balanced:+.2f} |", flush=True)
            print("", flush=True)

    print("DECAIMIENTO POR DEMORA (EV bruto, pooled 150 sesiones)", flush=True)
    print("una senal real decae con la demora; un artefacto muere de inmediato",
          flush=True)
    print("", flush=True)
    hdr = "| familia | bracket | " + " | ".join(f"{d}s" for d in DELAYS_S) + " |"
    print(hdr, flush=True)
    print("|" + "---|" * (len(DELAYS_S) + 2), flush=True)
    for fam in families:
        for k in BRACKETS:
            s = out[out["cost"].eq(1.8) & out["sample"].eq("ALL")
                    & out["family"].eq(fam) & out["bracket"].eq(k)]
            if not len(s):
                continue
            cells_txt = []
            for d in DELAYS_S:
                v = s[s["delay_s"].eq(d)]["gross_ev"]
                cells_txt.append(f"{v.iloc[0]:+.3f}" if len(v) else "-")
            print(f"| {fam} | {k} | " + " | ".join(cells_txt) + " |", flush=True)

    print("", flush=True)
    print(f"VEREDICTO: avanza solo si la cota inferior AJUSTADA OOS supera "
          f"{ADVANCE_BAR}", flush=True)
    print("", flush=True)
    any_pass = False
    for c in COSTS:
        s = out[out["cost"].eq(c) & out["sample"].eq("OOS")]
        if not len(s):
            continue
        b = s.loc[s["lo_adj"].idxmax()]
        ok = bool(b["lo_adj"] > ADVANCE_BAR)
        any_pass |= ok
        print(f"  costo {c}: mejor cota inferior = {b['lo_adj']:+.3f} "
              f"({b['family']} d={b['delay_s']}s k={int(b['bracket'])}) -> "
              f"{'AVANZA' if ok else 'NO avanza'}", flush=True)
        inc = s[s["hi_adj"] > ADVANCE_BAR]
        print(f"      cotas SUPERIORES que excluyen {ADVANCE_BAR}: "
              f"{len(s) - len(inc)} de {len(s)}", flush=True)
        for r in inc.itertuples():
            print(f"      INCONCLUSA: {r.family} d={r.delay_s}s k={int(r.bracket)} "
                  f"neto {r.net_ev:+.3f} ajustado "
                  f"[{r.lo_adj:+.3f}, {r.hi_adj:+.3f}] (n={r.n})", flush=True)
        sa = out[out["cost"].eq(c) & out["sample"].eq("ALL")]
        if len(sa):
            print(f"      pooled: cota superior ajustada maxima = "
                  f"{sa['hi_adj'].max():+.3f} "
                  f"({'todas excluyen' if sa['hi_adj'].max() <= ADVANCE_BAR else 'alguna NO excluye'}"
                  f" {ADVANCE_BAR})", flush=True)
    print("", flush=True)
    print(f"  CONCLUSION: {'hay celda que avanza' if any_pass else 'NINGUNA celda avanza'}",
          flush=True)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
