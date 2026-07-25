"""Evaluate the frozen AMD-2 consensus stability endpoint without outcomes."""

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


def load_label_csv(path: Path, field: str = "label") -> dict[str, str]:
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
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--claude", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases-output", type=Path, required=True)
    args = parser.parse_args()

    original = load_label_csv(args.original, "consensus_label")
    claude = load_label_csv(args.claude)
    codex = load_label_csv(args.codex)
    if not (set(original) == set(claude) == set(codex)):
        raise ValueError("CaseID sets differ")

    case_rows: list[dict[str, object]] = []
    original_ab = [
        case_id for case_id, label in original.items() if label in {"A", "B"}
    ]
    flips = 0
    new_counts = Counter()
    for case_id in sorted(original):
        new = consensus(claude[case_id], codex[case_id])
        new_counts[new] += 1
        in_primary = original[case_id] in {"A", "B"}
        flip = in_primary and new != original[case_id]
        flips += int(flip)
        case_rows.append(
            {
                "CaseID": case_id,
                "original_consensus": original[case_id],
                "claude_perturbed": claude[case_id],
                "codex_perturbed": codex[case_id],
                "new_consensus": new,
                "in_primary_denominator": str(in_primary).lower(),
                "primary_flip": str(flip).lower(),
                "information_status": "AMD2_STABILITY_NO_OUTCOME",
            }
        )
    denominator = len(original_ab)
    flip_rate = flips / denominator
    exact_all = sum(
        row["original_consensus"] == row["new_consensus"]
        for row in case_rows
    )
    new_ab_agree = sum(
        row["new_consensus"] in {"A", "B"} for row in case_rows
    )
    result = {
        "protocol": "HUMAN_BLIND_V1_AMD2_STABILITY_V1",
        "outcome_loaded": False,
        "mapping_loaded": False,
        "primary_endpoint": {
            "original_ab_denominator": denominator,
            "flips": flips,
            "flip_rate": flip_rate,
            "threshold_max": 0.10,
            "pass": flip_rate <= 0.10,
        },
        "secondary": {
            "exact_consensus_all_98": exact_all,
            "exact_consensus_all_98_rate": exact_all / 98,
            "new_consensus_ab": new_ab_agree,
            "new_consensus_counts": dict(sorted(new_counts.items())),
        },
        "input_sha256": {
            "original_consensus": sha256_file(args.original),
            "claude_perturbed": sha256_file(args.claude),
            "codex_perturbed": sha256_file(args.codex),
        },
        "interpretation_limit": (
            "This measures stability to a cosmetic render perturbation only; "
            "it does not measure predictive separation or correctness."
        ),
    }
    args.cases_output.parent.mkdir(parents=True, exist_ok=True)
    with args.cases_output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(case_rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(case_rows)
    result["cases_output_sha256"] = sha256_file(args.cases_output)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["primary_endpoint"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
