"""Run the frozen V2 extraction (P0 + P1:P5 + MIRROR) and stability gates.

Order enforced by V2_PREREGISTRO_CONVERGENTE.md:
  - extractor code hashed BEFORE this script touches the 98 real cases;
  - scales s_j computed once from P0 discovery (2022-2023) inputs, reused
    frozen for every perturbation;
  - stability gates evaluated on discovery cases only;
  - no outcome of any kind is read or written here.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from progress import track
from v2_extractor import (
    CaseInputs, compute_scales, extract_raw, load_case, mirror_case,
    quantize_times_1ms, score_case, sha256_file,
)

BASE = Path(__file__).resolve().parent
HANDOFF = (BASE.parent / "mechanical_book_v1"
           / "MECHANICAL_BOOK_HANDOFF_AUDIT_98.csv")
OUT = BASE / "output"
DISCOVERY_YEARS = {2022, 2023}

PERTURBATIONS = ("P1", "P2", "P3", "P4", "P5")


def extract_variant(row: pd.Series, case: CaseInputs, name: str):
    if name == "P0":
        return extract_raw(case)
    if name == "P1":
        return extract_raw(quantize_times_1ms(case))
    if name == "P2":
        return extract_raw(case, grid_ms=10, grid_phase_ms=0.0)
    if name == "P3":
        return extract_raw(case, grid_ms=10, grid_phase_ms=5.0)
    if name == "P4":
        return extract_raw(load_case(row, permute_p4=True))
    if name == "P5":
        return extract_raw(case, p5_round=True)
    if name == "MIRROR":
        return extract_raw(mirror_case(case))
    raise ValueError(name)


def gate_for(name: str, base_rows: pd.DataFrame,
             pert_rows: pd.DataFrame) -> dict:
    """Frozen stability gate for one perturbation, discovery cases only."""
    merged = base_rows.merge(pert_rows, on="BurstId",
                             suffixes=("_0", "_p"))
    eval0 = merged[merged["evaluable_0"]]
    both = eval0[eval0["evaluable_p"]]
    retention = len(both) / len(eval0) if len(eval0) else 0.0
    result = {"perturbation": name, "n_eval_P0": int(len(eval0)),
              "n_eval_both": int(len(both)), "retention": retention}
    if len(both) < 3:
        result.update({"PASS": False, "reason": "insufficient overlap"})
        return result
    s0 = both["S_0"].to_numpy()
    sp = both["S_p"].to_numpy()
    q0 = both["Q_0"].to_numpy()
    qp = both["Q_p"].to_numpy()
    rho = spearmanr(s0, sp).statistic
    d_s = np.abs(sp - s0)
    d_q = np.abs(qp - q0)
    strong = np.sum(((s0 > 0.15) & (sp < -0.15))
                    | ((s0 < -0.15) & (sp > 0.15)))
    checks = {
        "spearman": float(rho) if np.isfinite(rho) else None,
        "spearman_pass": bool(np.isfinite(rho) and rho >= 0.98),
        "median_abs_dS": float(np.median(d_s)),
        "median_pass": bool(np.median(d_s) <= 0.05),
        "p95_abs_dS": float(np.percentile(d_s, 95)),
        "p95_pass": bool(np.percentile(d_s, 95) <= 0.15),
        "strong_flips": int(strong),
        "flip_rate": float(strong / len(both)),
        "flip_pass": bool(strong <= 1 and strong / len(both) <= 0.02),
        "retention_pass": bool(retention >= 0.95),
        "p95_abs_dQ": float(np.percentile(d_q, 95)),
        "dq_pass": bool(np.percentile(d_q, 95) <= 0.05),
    }
    result.update(checks)
    result["PASS"] = all(
        checks[k] for k in ("spearman_pass", "median_pass", "p95_pass",
                            "flip_pass", "retention_pass", "dq_pass")
    )
    return result


def main() -> int:
    t_start = time.time()
    OUT.mkdir(exist_ok=True)
    handoff = pd.read_csv(HANDOFF)
    if len(handoff) != 98:
        raise ValueError(f"Expected 98 rows, got {len(handoff)}")
    handoff = handoff.sort_values(["fecha", "BurstId"]).reset_index(drop=True)
    handoff["year"] = handoff["fecha"].astype(str).str[:4].astype(int)

    # ---- pass 1: load + extract all variants per case (single DBN read)
    raw_by_variant: dict[str, list] = {v: [] for v in
                                       ("P0",) + PERTURBATIONS + ("MIRROR",)}
    rows_iter = list(handoff.iterrows())
    for _, row in track(rows_iter, label="extract 98 casos x 7 variantes"):
        t_case = time.time()
        case = load_case(row)
        is_discovery = int(row["year"]) in DISCOVERY_YEARS
        raw_by_variant["P0"].append(extract_variant(row, case, "P0"))
        if is_discovery:
            for name in PERTURBATIONS + ("MIRROR",):
                raw_by_variant[name].append(extract_variant(row, case, name))
        if time.time() - t_case > 30:
            print(f"  [slow] {row['BurstId']} {time.time()-t_case:.1f}s")

    print(f"[{time.time()-t_start:.0f}s] extraccion completa")

    # ---- scales from P0 discovery only, frozen for every variant
    scales = compute_scales(raw_by_variant["P0"], DISCOVERY_YEARS)
    (OUT / "V2_SCALES.json").write_text(
        json.dumps(scales, indent=2), encoding="utf-8"
    )

    # ---- score all variants with the same frozen scales
    frames = {}
    for name, raws in raw_by_variant.items():
        frame = pd.DataFrame([score_case(rr, scales) for rr in raws])
        frames[name] = frame
    frames["P0"].to_csv(OUT / "V2_SCORES_P0_98.csv", index=False)
    for name in PERTURBATIONS + ("MIRROR",):
        frames[name].to_csv(OUT / f"V2_SCORES_{name}_discovery.csv",
                            index=False)

    # ---- coverage gate on P0 discovery
    p0 = frames["P0"].copy()
    p0["year"] = p0["fecha"].astype(str).str[:4].astype(int)
    disc0 = p0[p0["year"].isin(DISCOVERY_YEARS)]
    n_eval_disc = int(disc0["evaluable"].sum())
    coverage_gate = n_eval_disc >= 56

    # ---- stability gates (discovery only)
    disc_base = disc0[["BurstId", "S", "Q", "evaluable"]].rename(
        columns={"S": "S_0", "Q": "Q_0", "evaluable": "evaluable_0"})
    gates = []
    for name in PERTURBATIONS:
        pert = frames[name][["BurstId", "S", "Q", "evaluable"]].rename(
            columns={"S": "S_p", "Q": "Q_p", "evaluable": "evaluable_p"})
        gates.append(gate_for(name, disc_base, pert))

    # MIRROR exact gate
    mir = frames["MIRROR"][["BurstId", "S", "Q", "evaluable"]].rename(
        columns={"S": "S_p", "Q": "Q_p", "evaluable": "evaluable_p"})
    mm = disc_base.merge(mir, on="BurstId")
    with np.errstate(invalid="ignore"):
        d_s = np.abs(mm["S_p"].to_numpy() - mm["S_0"].to_numpy())
        d_q = np.abs(mm["Q_p"].to_numpy() - mm["Q_0"].to_numpy())
    d_s = np.where(np.isnan(mm["S_0"]) & np.isnan(mm["S_p"]), 0.0, d_s)
    usab_changes = int((mm["evaluable_0"] != mm["evaluable_p"]).sum())
    mirror_gate = {
        "perturbation": "MIRROR",
        "max_abs_dS": float(np.nanmax(d_s)) if len(d_s) else None,
        "max_abs_dQ": float(np.nanmax(d_q)) if len(d_q) else None,
        "usability_changes": usab_changes,
        "PASS": bool(len(d_s) and np.nanmax(d_s) <= 1e-12
                     and np.nanmax(d_q) <= 1e-12 and usab_changes == 0),
    }
    gates.append(mirror_gate)

    joint_pass = coverage_gate and all(g["PASS"] for g in gates)
    summary = {
        "information_status": "V2_STABILITY_NO_OUTCOME",
        "n_cases_total": int(len(p0)),
        "n_discovery": int(len(disc0)),
        "n_eval_discovery_P0": n_eval_disc,
        "coverage_gate_min56": bool(coverage_gate),
        "hard_fails": p0["hard_fail"].replace("", np.nan).dropna().tolist(),
        "gates": gates,
        "JOINT_STABILITY": "PASS" if joint_pass else "FAIL",
        "elapsed_seconds": round(time.time() - t_start, 1),
    }
    (OUT / "V2_STABILITY_RESULT.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "gates"},
                     indent=2))
    for gate in gates:
        print(gate["perturbation"], "PASS" if gate["PASS"] else "FAIL")
    print(f"JOINT: {summary['JOINT_STABILITY']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
