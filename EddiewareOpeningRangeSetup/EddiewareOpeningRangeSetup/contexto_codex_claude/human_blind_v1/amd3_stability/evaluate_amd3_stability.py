"""Evaluate AMD-3 stable-core robustness without loading mappings or outcomes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_labels(path: Path, field: str) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result: dict[str, str] = {}
    for row in rows:
        case_id = row["CaseID"].strip()
        label = row[field].strip().upper()
        if case_id in result or label not in {"A", "B", "C"}:
            raise ValueError(f"Invalid row in {path.name}")
        result[case_id] = label
    if len(result) != 98:
        raise ValueError(f"{path.name}: expected 98 rows")
    return result


def consensus(claude: str, codex: str) -> str:
    if claude == codex and claude in {"A", "B"}:
        return claude
    return "C"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stable-core", type=Path, required=True)
    parser.add_argument("--claude", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases-output", type=Path, required=True)
    args = parser.parse_args()

    stable = load_labels(args.stable_core, "amd3_stable_core")
    claude = load_labels(args.claude, "label")
    codex = load_labels(args.codex, "label")
    if not (set(stable) == set(claude) == set(codex)):
        raise ValueError("CaseID sets differ")

    rows: list[dict[str, object]] = []
    flips = 0
    counts = Counter()
    transitions = Counter()
    for case_id in sorted(stable):
        new = consensus(claude[case_id], codex[case_id])
        counts[new] += 1
        transitions[(stable[case_id], new)] += 1
        primary = stable[case_id] in {"A", "B"}
        flip = primary and new != stable[case_id]
        flips += int(flip)
        rows.append(
            {
                "CaseID": case_id,
                "amd3_stable_core": stable[case_id],
                "claude_perturbation2": claude[case_id],
                "codex_perturbation2": codex[case_id],
                "perturbation2_consensus": new,
                "in_primary_denominator": str(primary).lower(),
                "primary_flip": str(flip).lower(),
                "information_status": "AMD3_STABILITY_NO_OUTCOME",
            }
        )
    denominator = sum(label in {"A", "B"} for label in stable.values())
    flip_rate = flips / denominator
    directional_flips = sum(
        count
        for (left, right), count in transitions.items()
        if left in {"A", "B"} and right in {"A", "B"} and left != right
    )
    args.cases_output.parent.mkdir(parents=True, exist_ok=True)
    with args.cases_output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    result = {
        "protocol": "HUMAN_BLIND_V1_AMD3_STABILITY_V1",
        "outcome_loaded": False,
        "mapping_loaded": False,
        "primary_endpoint": {
            "stable_core_ab_denominator": denominator,
            "flips": flips,
            "flip_rate": flip_rate,
            "threshold_max": 0.10,
            "pass": flip_rate <= 0.10,
        },
        "secondary": {
            "directional_a_b_flips": directional_flips,
            "perturbation2_consensus_counts": dict(sorted(counts.items())),
            "transitions": {
                f"{left}_to_{right}": count
                for (left, right), count in sorted(transitions.items())
            },
        },
        "input_sha256": {
            "stable_core": sha256_file(args.stable_core),
            "claude_perturbation2": sha256_file(args.claude),
            "codex_perturbation2": sha256_file(args.codex),
        },
        "cases_output_sha256": sha256_file(args.cases_output),
        "interpretation_limit": (
            "Stability is not predictive separation. Outcome remains sealed "
            "unless the primary gate passes."
        ),
    }
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["primary_endpoint"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
