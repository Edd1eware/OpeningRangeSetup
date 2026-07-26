"""Recompute only the P4 variant with the fixed round-trip regrouping and
re-evaluate the joint stability gate. Reuses the frozen P0 scores and scales
(P0/P1/P2/P3/P5/MIRROR are independent of the P4 code path)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from progress import track
from v2_extractor import extract_raw, load_case, score_case
from v2_run_extraction import BASE, HANDOFF, OUT, DISCOVERY_YEARS, gate_for

PERTURBATIONS = ("P1", "P2", "P3", "P4", "P5")


def main() -> int:
    t0 = time.time()
    scales = json.loads((OUT / "V2_SCALES.json").read_text())
    handoff = pd.read_csv(HANDOFF)
    handoff = handoff.sort_values(["fecha", "BurstId"]).reset_index(drop=True)
    handoff["year"] = handoff["fecha"].astype(str).str[:4].astype(int)
    disc = handoff[handoff["year"].isin(DISCOVERY_YEARS)]

    rows = []
    for _, row in track(list(disc.iterrows()), label="P4 fix 69 discovery"):
        raw = extract_raw(load_case(row, permute_p4=True))
        rows.append(score_case(raw, scales))
    p4 = pd.DataFrame(rows)
    p4.to_csv(OUT / "V2_SCORES_P4_discovery.csv", index=False)

    # rebuild gates from saved CSVs
    p0 = pd.read_csv(OUT / "V2_SCORES_P0_98.csv")
    p0["year"] = p0["fecha"].astype(str).str[:4].astype(int)
    disc0 = p0[p0["year"].isin(DISCOVERY_YEARS)]
    disc_base = disc0[["BurstId", "S", "Q", "evaluable"]].rename(
        columns={"S": "S_0", "Q": "Q_0", "evaluable": "evaluable_0"})

    gates = []
    for name in PERTURBATIONS:
        frame = pd.read_csv(OUT / f"V2_SCORES_{name}_discovery.csv")
        pert = frame[["BurstId", "S", "Q", "evaluable"]].rename(
            columns={"S": "S_p", "Q": "Q_p", "evaluable": "evaluable_p"})
        gates.append(gate_for(name, disc_base, pert))

    mir = pd.read_csv(OUT / "V2_SCORES_MIRROR_discovery.csv")
    mir = mir[["BurstId", "S", "Q", "evaluable"]].rename(
        columns={"S": "S_p", "Q": "Q_p", "evaluable": "evaluable_p"})
    mm = disc_base.merge(mir, on="BurstId")
    d_s = np.abs(mm["S_p"].to_numpy() - mm["S_0"].to_numpy())
    d_s = np.where(np.isnan(mm["S_0"]) & np.isnan(mm["S_p"]), 0.0, d_s)
    d_q = np.abs(mm["Q_p"].to_numpy() - mm["Q_0"].to_numpy())
    usab = int((mm["evaluable_0"] != mm["evaluable_p"]).sum())
    gates.append({
        "perturbation": "MIRROR",
        "max_abs_dS": float(np.nanmax(d_s)), "max_abs_dQ": float(np.nanmax(d_q)),
        "usability_changes": usab,
        "PASS": bool(np.nanmax(d_s) <= 1e-12 and np.nanmax(d_q) <= 1e-12
                     and usab == 0),
    })

    n_eval = int(disc0["evaluable"].sum())
    coverage = n_eval >= 56
    joint = coverage and all(g["PASS"] for g in gates)
    summary = {
        "information_status": "V2_STABILITY_NO_OUTCOME",
        "n_cases_total": int(len(p0)), "n_discovery": int(len(disc0)),
        "n_eval_discovery_P0": n_eval, "coverage_gate_min56": bool(coverage),
        "hard_fails": p0["hard_fail"].replace("", np.nan).dropna().tolist(),
        "gates": gates,
        "JOINT_STABILITY": "PASS" if joint else "FAIL",
        "elapsed_seconds": round(time.time() - t0, 1),
        "note": "P4 recomputed with round-trip regrouping fix; other variants reused",
    }
    (OUT / "V2_STABILITY_RESULT.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    for g in gates:
        print(g["perturbation"], "PASS" if g["PASS"] else "FAIL")
    print("JOINT:", summary["JOINT_STABILITY"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
