"""Volatility-scaled brackets, done properly, on a COMMON entry set.

Fixes two defects in script 23, both of which I found or conceded rather than
papering over.

Defect 1: P4 never tested volatility scaling
--------------------------------------------
Script 23 scaled the bracket by the trailing-60s print RANGE and then clipped it
to [8, 60] ticks. Measured on the IS half, that range has median 119 ticks and
a 5th percentile of 54, so the clip bound on essentially every decision and the
median stop actually used was 60 -- the ceiling. P4 therefore measured a FIXED
60/60 bracket under a label that said "volatility scaled". The conclusion drawn
from it was worthless.

Here the bracket is a declared FRACTION of that range, with the fractions chosen
so the resulting stops land in the regime the Lucid objective needs, using the
IS distribution only:

    f = 0.15  ->  stop p5 8,  median 18, p95 39 ticks
    f = 0.25  ->  stop p5 14, median 30, p95 64
    f = 0.50  ->  stop p5 27, median 60, p95 129

Clipping is to the IS 1st/99th percentile of (f x range), so it almost never
binds, and the bind rate is REPORTED rather than hidden.

Defect 2: the entry set depended on the policy
----------------------------------------------
Codex: "Bracket-dependent busy filtering does matter. At 40/40, imbalance skips
408/2878 = 14.18% of candidate decisions; at 8/8 it skips none. Those are
different entry populations. Comparing their means does not isolate the exit-rule
effect."

So every policy here reserves the SAME fixed 300-second slot after an entry,
regardless of when it actually exits. The entry set is then identical across
policies by construction, and the only thing that differs is the exit rule.
That is slightly conservative in trade count, and it is the price of a clean
comparison.

A fixed 20/20 bracket is included on the same common entry set as the reference,
so the volatility-scaled numbers are read against something comparable rather
than against script 21's differently-selected sample.

Statistics unchanged from script 21/23: primary outcome is NET ticks with a
session-level cluster bootstrap; no binomial tests; m = 3 families x 4 policies
= 12 cells and the reported interval IS the (1 - 0.05/12) one. Prior is low:
36 policies have already produced nothing. Anything positive here would still
need a season that has never been looked at, which 2026 cannot supply.
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
OUT = DATA / "reports" / "vol_scaled_common_entry.csv"

ENTRY_DELAY_S = 0.5
HORIZON_S = 300
SLOT_S = 300               # the COMMON occupancy slot, identical for all policies
VOL_WIN_S = 60
FACTORS = (0.15, 0.25, 0.50)
FIXED_REF = 20             # fixed-bracket reference on the same entry set
COSTS = (1.8, 2.8, 3.8)
N_BOOT = 50_000
SEED = 20261012
ADVANCE_BAR = 2.5


def walk_sym(st: SessionTape, i: int, d: int, k: int,
             t_limit_ns: int) -> tuple[float, str]:
    """Symmetric bracket walk. Fill at the crossing print (a defined proxy:
    stop overshoot hurts, target overshoot helps)."""
    e = st.px[i]
    j_end = int(np.searchsorted(st.ts, t_limit_ns, side="right"))
    if j_end <= i + 1:
        return 0.0, "no_path"
    fav = d * (st.px[i + 1:j_end] - e)
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

    last_tau = WIN_TO_S - HORIZON_S - ENTRY_DELAY_S - 1.0

    # ---- pass 1: build the COMMON entry set, once, per family ------------
    print("building common entry sets (fixed 300s slot, identical for every "
          "policy)...", flush=True)
    entries: dict = {}
    for fam, (mask, direction) in families.items():
        sel = mask & (direction != 0) & (dec["tau_s"].to_numpy() <= last_tau)
        sub = dec[sel].copy()
        sub["d"] = direction[sel]
        sub = sub.sort_values(["session", "tau_s"])
        rows = []
        skipped = 0
        for sess, g in sub.groupby("session", sort=True):
            st = groups.get(sess)
            if st is None:
                continue
            busy = -1
            for r in g.itertuples():
                tau_ns = st.open_ns + int(r.tau_s * NS)
                e_ns = tau_ns + int(ENTRY_DELAY_S * NS)
                if e_ns < busy:
                    skipped += 1
                    continue
                i = int(np.searchsorted(st.ts, e_ns, side="left"))
                if i >= len(st.ts):
                    continue
                if st.ts[i] + int(HORIZON_S * NS) > st.open_ns + int(WIN_TO_S * NS):
                    continue
                # sigma from [tau-60s, tau): strictly before the decision
                a = int(np.searchsorted(st.ts, tau_ns - int(VOL_WIN_S * NS), "left"))
                bq = int(np.searchsorted(st.ts, tau_ns, "left"))
                if bq - a < 5:
                    continue
                sigma = int(st.px[a:bq].max() - st.px[a:bq].min())
                rows.append((sess, i, int(r.d), sigma))
                busy = st.ts[i] + int(SLOT_S * NS)   # SAME slot for all policies
        entries[fam] = rows
        print(f"  {fam:<11} {len(rows):,} entradas comunes "
              f"({skipped:,} descartadas por ocupacion)", flush=True)

    # clips from the IS half of sigma only
    clips = {}
    for f in FACTORS:
        vals = np.array([f * s for fam in entries for (sess, _, _, s) in entries[fam]
                         if sess in is_set])
        clips[f] = (int(max(2, np.percentile(vals, 1))), int(np.percentile(vals, 99)))
        print(f"  clip f={f:.2f}: [{clips[f][0]}, {clips[f][1]}] ticks "
              f"(IS p1/p99)", flush=True)

    m_cells = len(families) * (len(FACTORS) + 1)
    adj = 1.0 - 0.05 / m_cells
    print(f"cells = {m_cells}; reporting the {adj:.4%} interval (applied)",
          flush=True)

    policies = [(f"vol_f{f:.2f}", f) for f in FACTORS] + [("fixed_20", None)]

    rng = np.random.default_rng(SEED)
    rows_out = []
    cells = [(fam, pn) for fam in families for pn, _ in policies]
    pol_map = dict(policies)

    for fam, pname in track(cells, label="vol-scaled cells"):
        f = pol_map[pname]
        recs = []
        n_bind = 0
        for sess, i, d, sigma in entries[fam]:
            st = groups[sess]
            if f is None:
                k = FIXED_REF
            else:
                raw = f * sigma
                lo, hi = clips[f]
                k = int(round(min(max(raw, lo), hi)))
                n_bind += int(raw < lo or raw > hi)
            t_limit = st.ts[i] + int(HORIZON_S * NS)
            gross, kind = walk_sym(st, i, d, k, t_limit)
            if kind == "no_path":
                continue
            recs.append((sess, gross, d, kind, k))
        if len(recs) < 30:
            continue
        rec = pd.DataFrame(recs, columns=["session", "ticks", "d", "kind", "k"])

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
                rows_out.append(dict(
                    family=fam, policy=pname, sample=sample, cost=c,
                    n=len(t), n_sessions=int((cnts > 0).sum()),
                    wr=float((gross > 0).mean()),
                    gross_ev=float(gross.mean()), net_ev=float(gross.mean() - c),
                    lo95=ci[0.95][0], hi95=ci[0.95][1],
                    lo_adj=ci[adj][0], hi_adj=ci[adj][1],
                    dir_balanced=float((lo_leg.mean() + sh_leg.mean()) / 2)
                    if len(lo_leg) and len(sh_leg) else np.nan,
                    median_k=float(np.median(t["k"])),
                    p5_k=float(np.percentile(t["k"], 5)),
                    p95_k=float(np.percentile(t["k"], 95)),
                    bind_rate=float(n_bind / max(len(entries[fam]), 1)),
                    n_timeout=int((t["kind"] == "timeout").sum()),
                ))

    out = pd.DataFrame(rows_out)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    print("", flush=True)
    print("=" * 118, flush=True)
    print("BRACKET ESCALADO POR VOLATILIDAD, entrada COMUN. "
          "Primario = EV NETO en ticks.", flush=True)
    print("", flush=True)
    base = out[out["cost"].eq(1.8)]
    for fam in families:
        print(f"--- {fam}, costo 1.8 ---", flush=True)
        print("| politica | muestra | n | WR | SL med (p5-p95) | clip liga | "
              f"EV bruto | EV neto | IC95 | IC{adj:.2%} | balanceado dir |",
              flush=True)
        print("|---|---|---|---|---|---|---|---|---|---|---|", flush=True)
        for r in base[base["family"].eq(fam)].sort_values(["policy", "sample"]).itertuples():
            print(f"| {r.policy} | {r.sample} | {r.n:,} | {r.wr:.1%} | "
                  f"{r.median_k:.0f} ({r.p5_k:.0f}-{r.p95_k:.0f}) | "
                  f"{r.bind_rate:.1%} | {r.gross_ev:+.2f} | **{r.net_ev:+.2f}** | "
                  f"[{r.lo95:+.2f}, {r.hi95:+.2f}] | "
                  f"[{r.lo_adj:+.2f}, {r.hi_adj:+.2f}] | "
                  f"{r.dir_balanced:+.2f} |", flush=True)
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
