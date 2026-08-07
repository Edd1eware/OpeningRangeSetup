from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "artifacts" / "post_lb_regime_audit_integrity_v3"
OUTPUT = ROOT / "artifacts" / "resolved_threshold_audit_v3"
TABLE_PATH = OUTPUT / "resolved_threshold_audit.csv"
REPORT_PATH = OUTPUT / "REPORT.md"
MANIFEST_PATH = OUTPUT / "manifest.json"
CONFIG_PATH = ROOT / "config" / "post_lb_regime_config.json"

RESOLVED = ("CONTINUATION", "REVERSAL", "NO_EXPANSION")
HIERARCHY = (8, 12, 4, 16)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    gates = config["target_gates"]
    labels = pd.read_parquet(SOURCE / "regime_labels.parquet")
    v1_gates = pd.read_csv(SOURCE / "outcome_threshold_audit.csv")
    primary = labels[
        labels["reference"].eq("MID")
        & labels["horizon_ms"].eq(
            int(config["primary_horizon_ms"])
        )
        & labels["ambiguity_window_ms"].eq(
            int(config["ambiguity_window_ms"])
        )
    ]
    records: list[dict[str, object]] = []
    for threshold in HIERARCHY:
        all_rows = primary[
            primary["threshold_ticks"].eq(threshold)
        ]
        resolved = all_rows[all_rows["regime"].isin(RESOLVED)]
        counts = resolved["regime"].value_counts()
        shares = counts / max(len(resolved), 1)
        side_counts = pd.crosstab(
            resolved["lb_side"],
            resolved["regime"],
        ).reindex(
            index=["BUY", "SELL"],
            columns=RESOLVED,
            fill_value=0,
        )
        side_probabilities = side_counts.div(
            side_counts.sum(axis=1),
            axis=0,
        )
        resolved_tvd = float(
            0.5
            * np.abs(
                side_probabilities.loc["BUY"]
                - side_probabilities.loc["SELL"]
            ).sum()
        )
        session_counts = pd.crosstab(
            resolved["session_date"],
            resolved["regime"],
        ).reindex(columns=RESOLVED, fill_value=0)
        minimum_count = min(
            int(counts.get(regime, 0)) for regime in RESOLVED
        )
        maximum_share = max(
            float(shares.get(regime, 0.0)) for regime in RESOLVED
        )
        minimum_sessions = min(
            int((session_counts[regime] > 0).sum())
            for regime in RESOLVED
        )
        maximum_concentration = max(
            float(
                session_counts[regime].max()
                / max(session_counts[regime].sum(), 1)
            )
            for regime in RESOLVED
        )
        source_row = v1_gates[
            v1_gates["threshold_ticks"].eq(threshold)
        ].iloc[0]
        ambiguous_share = float(
            all_rows["regime"].eq("AMBIGUOUS").mean()
        )
        checks = {
            "coverage_pass": float(source_row["reference_coverage"])
            >= float(gates["min_reference_coverage"]),
            "resolved_class_count_pass": minimum_count
            >= int(gates["min_count_each_class"]),
            "resolved_degeneracy_pass": maximum_share
            <= float(gates["max_single_class_share"]),
            "ambiguity_share_pass": ambiguous_share
            <= float(gates["max_ambiguous_share"]),
            "resolved_side_symmetry_pass": resolved_tvd
            <= float(gates["max_buy_sell_total_variation"]),
            "resolved_session_presence_pass": minimum_sessions
            >= int(gates["min_sessions_each_class"]),
            "resolved_session_concentration_pass": maximum_concentration
            <= float(
                gates["max_session_concentration_each_class"]
            ),
            "reference_agreement_pass": float(
                source_row["mid_executable_agreement"]
            )
            >= float(gates["min_mid_executable_agreement"]),
            "ambiguity_stability_pass": float(
                source_row["ambiguity_window_min_agreement"]
            )
            >= float(gates["min_ambiguity_window_agreement"]),
            "threshold_stability_pass": float(
                source_row["threshold_perturbation_min_agreement"]
            )
            >= float(
                gates["min_threshold_perturbation_agreement"]
            ),
            "horizon_stability_pass": float(
                source_row["horizon_perturbation_min_agreement"]
            )
            >= float(gates["min_horizon_perturbation_agreement"]),
        }
        all_class_tvd = float(
            source_row["buy_sell_total_variation"]
        )
        records.append(
            {
                "threshold_ticks": threshold,
                "continuation_count": int(
                    counts.get("CONTINUATION", 0)
                ),
                "reversal_count": int(counts.get("REVERSAL", 0)),
                "no_expansion_count": int(
                    counts.get("NO_EXPANSION", 0)
                ),
                "ambiguous_count": int(
                    all_rows["regime"].eq("AMBIGUOUS").sum()
                ),
                "resolved_count": int(len(resolved)),
                "reference_coverage": float(
                    source_row["reference_coverage"]
                ),
                "minimum_resolved_class_count": minimum_count,
                "maximum_resolved_class_share": maximum_share,
                "ambiguous_share": ambiguous_share,
                "resolved_buy_sell_tvd": resolved_tvd,
                "all_class_buy_sell_tvd": all_class_tvd,
                "tvd_scope_changes_pass_fail": bool(
                    (resolved_tvd <= 0.15)
                    != (all_class_tvd <= 0.15)
                ),
                "minimum_sessions_each_resolved_class": (
                    minimum_sessions
                ),
                "maximum_resolved_session_concentration": (
                    maximum_concentration
                ),
                "mid_executable_agreement": float(
                    source_row["mid_executable_agreement"]
                ),
                "ambiguity_window_min_agreement": float(
                    source_row["ambiguity_window_min_agreement"]
                ),
                "threshold_perturbation_min_agreement": float(
                    source_row[
                        "threshold_perturbation_min_agreement"
                    ]
                ),
                "horizon_perturbation_min_agreement": float(
                    source_row["horizon_perturbation_min_agreement"]
                ),
                **checks,
                "pass": all(checks.values()),
            }
        )
    table = pd.DataFrame(records)
    selected = next(
        (
            threshold
            for threshold in HIERARCHY
            if bool(
                table.loc[
                    table["threshold_ticks"].eq(threshold),
                    "pass",
                ].iloc[0]
            )
        ),
        None,
    )
    if selected != 16:
        raise AssertionError(
            f"frozen resolved hierarchy selected {selected}, expected 16"
        )
    if bool(table["tvd_scope_changes_pass_fail"].any()):
        raise AssertionError("TVD scope changes a threshold verdict")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(TABLE_PATH, index=False, lineterminator="\n")
    report = f"""# Auditoría de thresholds resueltos V3

Fecha: 2026-07-27

Fuente: matriz V1 corregida y congelada, cinco sesiones técnicas, 106/111
referencias MID válidas.

Jerarquía consumida:

```text
8 -> 12 -> 4 -> 16
```

Resultado:

- 8 ticks: FAIL por TVD resuelta 0.167667 > 0.15;
- 12 ticks: FAIL por TVD resuelta 0.187523 > 0.15;
- 4 ticks: FAIL porque `NO_EXPANSION=0`;
- 16 ticks: PASS de todos los gates resueltos.

Threshold seleccionado mecánicamente: `{selected}` ticks.

El resultado es invariante a calcular TVD con o sin `AMBIGUOUS`: ningún
threshold cambia PASS/FAIL.

La jerarquía queda consumida. Si 16 ticks falla discovery no se vuelve a
8/12/4 y no se recorre otra vez.

`INFORMATION_STATUS=RESOLVED_THRESHOLD_V3_SELECTED_16T`
"""
    REPORT_PATH.write_text(report, encoding="utf-8")
    manifest = {
        "audit_id": "POST_LB_RESOLVED_THRESHOLD_AUDIT_V3",
        "selected_threshold_ticks": selected,
        "hierarchy_consumed": True,
        "tvd_scope_invariant": True,
        "files": {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in (TABLE_PATH, REPORT_PATH)
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
