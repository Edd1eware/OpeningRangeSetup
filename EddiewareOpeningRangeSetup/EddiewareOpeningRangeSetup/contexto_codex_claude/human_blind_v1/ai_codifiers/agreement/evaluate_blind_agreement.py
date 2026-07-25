"""Evaluate nominal agreement without loading mappings, dates, or outcomes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from itertools import combinations
from pathlib import Path


ALLOWED_LABELS = {"A", "B", "C"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_labels(path: Path, coder: str) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"CaseID", "label"}
    missing = required - set(rows[0] if rows else {})
    if missing:
        raise ValueError(f"{coder}: missing columns {sorted(missing)}")
    result: dict[str, str] = {}
    for row in rows:
        case_id = str(row["CaseID"]).strip()
        label = str(row["label"]).strip().upper()
        if not case_id or label not in ALLOWED_LABELS:
            raise ValueError(f"{coder}: invalid row {row}")
        if case_id in result:
            raise ValueError(f"{coder}: duplicate CaseID {case_id}")
        result[case_id] = label
    if len(result) != 98:
        raise ValueError(f"{coder}: expected 98 cases, found {len(result)}")
    return result


def krippendorff_alpha_nominal(coders: dict[str, dict[str, str]]) -> float:
    case_ids = sorted(next(iter(coders.values())))
    total_pairs = 0
    disagreement_pairs = 0
    pooled = Counter()
    for case_id in case_ids:
        labels = [values[case_id] for values in coders.values()]
        pooled.update(labels)
        for left, right in combinations(labels, 2):
            total_pairs += 1
            disagreement_pairs += int(left != right)
    observed = disagreement_pairs / total_pairs
    n = sum(pooled.values())
    expected_agreement = sum(
        count * (count - 1) for count in pooled.values()
    ) / (n * (n - 1))
    expected_disagreement = 1.0 - expected_agreement
    if expected_disagreement <= 0:
        return 1.0
    return 1.0 - observed / expected_disagreement


def pairwise_metrics(
    left: dict[str, str],
    right: dict[str, str],
) -> dict[str, float | int]:
    case_ids = sorted(left)
    matches = sum(left[case_id] == right[case_id] for case_id in case_ids)
    observed = matches / len(case_ids)
    left_counts = Counter(left.values())
    right_counts = Counter(right.values())
    expected = sum(
        left_counts[label] * right_counts[label] for label in ALLOWED_LABELS
    ) / (len(case_ids) ** 2)
    kappa = (
        (observed - expected) / (1.0 - expected)
        if expected < 1.0
        else 1.0
    )
    return {
        "n": len(case_ids),
        "matches": matches,
        "agreement": observed,
        "cohen_kappa": kappa,
    }


def evaluate(paths: dict[str, Path]) -> dict[str, object]:
    coders = {
        coder: load_labels(path, coder) for coder, path in paths.items()
    }
    id_sets = {tuple(sorted(values)) for values in coders.values()}
    if len(id_sets) != 1:
        raise ValueError("Coders do not contain the same CaseID set")
    pairwise = {}
    for left, right in combinations(coders, 2):
        pairwise[f"{left}__{right}"] = pairwise_metrics(
            coders[left],
            coders[right],
        )
    case_ids = sorted(next(iter(coders.values())))
    unanimous = 0
    majority = 0
    all_different = 0
    for case_id in case_ids:
        counts = Counter(values[case_id] for values in coders.values())
        maximum = max(counts.values())
        unanimous += maximum == len(coders)
        majority += maximum >= 2
        all_different += maximum == 1
    alpha = krippendorff_alpha_nominal(coders)
    return {
        "protocol": "HUMAN_BLIND_V1_AMD1",
        "information_scope": (
            "CaseID and blind A/B/C labels only; no mapping, date, side, "
            "family, result, MFE, MAE, TP, SL, or PnL loaded"
        ),
        "coders": list(coders),
        "n_cases": len(case_ids),
        "krippendorff_alpha_nominal": alpha,
        "operational_gate_threshold": 0.60,
        "operational_gate_pass": alpha >= 0.60,
        "unanimous_cases": unanimous,
        "majority_cases": majority,
        "all_different_cases": all_different,
        "label_counts": {
            coder: dict(sorted(Counter(values.values()).items()))
            for coder, values in coders.items()
        },
        "pairwise": pairwise,
        "input_sha256": {
            coder: sha256_file(path) for coder, path in paths.items()
        },
        "interpretation_limit": (
            "Agreement measures rubric reproducibility only. It is not "
            "evidence that labels predict clean absorption or clean breakout."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--human", type=Path)
    parser.add_argument("--claude", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {"CLAUDE": args.claude, "CODEX": args.codex}
    if args.human is not None:
        paths = {"EDUARDO": args.human, **paths}
    result = evaluate(paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["operational_gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
