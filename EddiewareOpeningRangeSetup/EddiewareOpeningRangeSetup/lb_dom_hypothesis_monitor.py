"""Monitor causal de separacion entre absorcion y continuacion limpias.

La variable DOM primaria se mide en t0. El outcome posterior solo etiqueta
ABSORCION LIMPIA, CONTINUACION LIMPIA o TRADE VARIABLE. El porcentaje es AUC
A-vs-B (50% equivale a azar), no WR ni probabilidad de ganar.
"""

from __future__ import annotations

from pathlib import Path
import re

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

import absorption_breakout_research as research


PRIMARY_FEATURE = "DOM_Ahead_Depth_Per_Aggressive_L3"
STATUS_FILE = "telegram_lb_hypothesis.txt"
MIN_CLASS_ROWS = 2


def _completed_sessions(root: Path) -> int:
    run_root = (
        root / "visual_tests" /
        "04_run_replay_lb_clean_ab_dom_r3_dst_2025_2026_runs"
    )
    if run_root.exists():
        dates = set()
        for path in run_root.glob("X10_*/score_trade_result_*_NY.csv"):
            match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
            if match:
                dates.add(match.group(1))
        if dates:
            return len(dates)

    sent_dates = root / "telegram_sent_dates.txt"
    if not sent_dates.exists():
        return 0
    try:
        return len({
            line.strip()
            for line in sent_dates.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        })
    except (OSError, UnicodeDecodeError):
        return 0


def _boolean(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "si"})


def calculate(results_folder: Path | str) -> dict[str, object]:
    root = Path(results_folder)
    dataset, audit = research.build_dataset(root)
    result: dict[str, object] = {
        "status": "CALCULANDO",
        "feature": PRIMARY_FEATURE,
        "auc": None,
        "percentage": None,
        "eligible": 0,
        "valid_dom": 0,
        "n_a": 0,
        "n_b": 0,
        "n_c": 0,
        "coverage": 0.0,
        "sessions": _completed_sessions(root),
        "audit": audit.to_dict("records") if not audit.empty else [],
    }
    if dataset.empty or PRIMARY_FEATURE not in dataset:
        return result

    eligible = dataset.loc[
        dataset["causal_row_flag"].astype(bool)
        & dataset["family"].isin(research.ANALYSIS_FAMILIES)
    ].copy()
    if "Detector_VERSION" in eligible:
        eligible = eligible.loc[
            eligible["Detector_VERSION"].astype(str).eq(research.EXPECTED_BURST_VERSION)
        ].copy()
    result["eligible"] = len(eligible)
    if eligible.empty:
        return result

    values = pd.to_numeric(eligible[PRIMARY_FEATURE], errors="coerce")
    dom_valid = _boolean(
        eligible.get("DOM_Snapshot_Valid", pd.Series(False, index=eligible.index))
    )
    valid_mask = values.notna() & np.isfinite(values) & dom_valid
    valid = eligible.loc[valid_mask].copy()
    valid[PRIMARY_FEATURE] = values.loc[valid_mask]
    result["valid_dom"] = len(valid)
    result["coverage"] = len(valid) / len(eligible) if len(eligible) else 0.0
    result["n_a"] = int(valid["family"].eq(research.FAMILY_ABSORPTION).sum())
    result["n_b"] = int(valid["family"].eq(research.FAMILY_CONTINUATION).sum())
    result["n_c"] = int(valid["family"].eq(research.FAMILY_VARIABLE).sum())
    if result["n_a"] < MIN_CLASS_ROWS or result["n_b"] < MIN_CLASS_ROWS:
        return result

    clean = valid.loc[
        valid["family"].isin([research.FAMILY_ABSORPTION, research.FAMILY_CONTINUATION])
    ]
    target_absorption = clean["family"].eq(research.FAMILY_ABSORPTION).astype(int)
    # A larger wall-ahead/aggression ratio is the preregistered absorption
    # direction; therefore AUC > 0.50 supports clean A/B separation.
    auc = float(roc_auc_score(target_absorption, clean[PRIMARY_FEATURE]))
    result["auc"] = auc
    result["percentage"] = 100.0 * auc
    result["status"] = "PROVISIONAL"
    return result


def format_status(result: dict[str, object]) -> str:
    prefix = "Efectividad del DOM antes del movimiento :"
    sessions = int(result.get("sessions", 0))
    if result.get("percentage") is None:
        return f"{prefix} CALCULANDO {sessions} sesiones"
    return f"{prefix} {float(result['percentage']):.1f}% {sessions} sesiones"


def update_status_file(results_folder: Path | str) -> str:
    root = Path(results_folder)
    root.mkdir(parents=True, exist_ok=True)
    try:
        line = format_status(calculate(root))
    except Exception:
        line = "Efectividad del DOM antes del movimiento : CALCULANDO 0 sesiones"
    (root / STATUS_FILE).write_text(line + "\n", encoding="utf-8")
    return line


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_folder", type=Path)
    args = parser.parse_args()
    print(update_status_file(args.results_folder))
