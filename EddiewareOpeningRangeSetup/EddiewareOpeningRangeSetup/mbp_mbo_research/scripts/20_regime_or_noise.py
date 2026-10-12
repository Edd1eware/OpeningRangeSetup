"""Is the IS->OOS sign flip a regime change, or is it just noise?

This answers the first question Codex raised about the markout results. It
matters because the two readings lead to opposite actions:

    regime change  -> the signal exists but is unstable; look for a regime
                      filter, and the IS/OOS split is confounded (which Codex
                      already warned about in round 2)
    noise          -> there is nothing to filter, and the dramatic-looking flip
                      is an artefact of where the split happened to land

Method: drop the IS/OOS split entirely and look at the markout MONTH by month,
each with its own session-level bootstrap. A regime change should show a clean
break with months that are individually away from zero. Noise should wander
across zero with every interval covering it.

Reads the decision table that 18_absorption_drive.py persists, so it adds no
new estimation choices: same frozen tail cutoff, same primary cell.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import DATA  # noqa: E402
from tape_lib import IS_SESSIONS, TAIL_Q, N_BOOT, SEED  # noqa: E402

DEC = DATA / "tape" / "decisions_15s.parquet"
OUT = DATA / "reports" / "regime_or_noise.csv"
CELL = "mk_mid_0.5_15"      # the primary cell, fixed in advance


def boot_ci(vals: np.ndarray, keys: np.ndarray,
            rng: np.random.Generator) -> tuple[float, float]:
    uniq = np.unique(keys)
    idx = {k: np.flatnonzero(keys == k) for k in uniq}
    draws = np.array([
        vals[np.concatenate([idx[k] for k in rng.choice(uniq, len(uniq), True)])].mean()
        for _ in range(N_BOOT)
    ])
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def main() -> None:
    d = pd.read_parquet(DEC)
    sessions = np.array(sorted(d["session"].unique()))
    is_set = set(sessions[:IS_SESSIONS])

    # same frozen cutoff as the studies: IS-only quantile of |imb|
    cut = float(np.quantile(
        np.abs(d.loc[d["session"].isin(is_set), "imb"].to_numpy()), TAIL_Q))

    direction = np.sign(d["imb"].to_numpy())
    m = ((np.abs(d["imb"].to_numpy()) >= cut)
         & d[CELL].notna().to_numpy() & (direction != 0))
    s = d[m].copy()
    s["signed"] = direction[m] * d[CELL].to_numpy()[m]
    s["month"] = pd.to_datetime(s["session"]).dt.to_period("M").astype(str)

    rng = np.random.default_rng(SEED)
    rows = []
    for mo, g in s.groupby("month"):
        lo, hi = boot_ci(g["signed"].to_numpy(), g["session"].to_numpy(), rng)
        rows.append(dict(month=mo, sessions=g["session"].nunique(), n=len(g),
                         markout_ticks=float(g["signed"].mean()),
                         lo95=lo, hi95=hi, covers_zero=bool(lo <= 0 <= hi)))
    res = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT, index=False)

    print(f"markout de la cola |imb| >= {cut:.4f}, celda {CELL}, POR MES", flush=True)
    print("", flush=True)
    print("| mes | sesiones | n | markout ticks | IC95 | cubre 0 |", flush=True)
    print("|---|---|---|---|---|---|", flush=True)
    for r in res.itertuples():
        print(f"| {r.month} | {r.sessions} | {r.n:,} | {r.markout_ticks:+.3f} | "
              f"[{r.lo95:+.2f}, {r.hi95:+.2f}] | "
              f"{'si' if r.covers_zero else 'NO'} |", flush=True)

    pos = int((res["markout_ticks"] > 0).sum())
    print("", flush=True)
    print(f"meses positivos: {pos} de {len(res)}", flush=True)
    print(f"rango mensual: {res['markout_ticks'].min():+.2f} a "
          f"{res['markout_ticks'].max():+.2f} ticks", flush=True)
    print(f"meses cuyo IC excluye 0: {int((~res['covers_zero']).sum())} "
          f"de {len(res)}", flush=True)

    per_sess = s.groupby("session")["signed"].mean()
    ins = per_sess[[x in is_set for x in per_sess.index]]
    oos = per_sess[[x not in is_set for x in per_sess.index]]
    print("", flush=True)
    print(f"sesiones IS  con markout > 0: {int((ins > 0).sum())} de {len(ins)} "
          f"({(ins > 0).mean():.0%})", flush=True)
    print(f"sesiones OOS con markout > 0: {int((oos > 0).sum())} de {len(oos)} "
          f"({(oos > 0).mean():.0%})", flush=True)
    print("", flush=True)
    print("LECTURA: si los meses alternan de signo y todos los IC cubren cero,", flush=True)
    print("no hay regimen que filtrar; el flip IS/OOS es donde cayo el corte.", flush=True)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
