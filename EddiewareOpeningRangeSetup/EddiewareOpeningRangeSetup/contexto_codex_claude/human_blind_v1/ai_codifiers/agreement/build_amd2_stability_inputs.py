"""Build outcome-blind AMD-2 consensus and cosmetic stability renders."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
from collections import Counter
from pathlib import Path

from PIL import Image


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_labels(path: Path, coder: str) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    labels: dict[str, str] = {}
    for row in rows:
        case_id = row["CaseID"].strip()
        label = row["label"].strip().upper()
        if case_id in labels or label not in {"A", "B", "C"}:
            raise ValueError(f"{coder}: invalid label row")
        labels[case_id] = label
    if len(labels) != 98:
        raise ValueError(f"{coder}: expected 98 labels")
    return labels


def consensus_label(claude: str, codex: str) -> str:
    if claude == codex and claude in {"A", "B"}:
        return claude
    return "C"


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def perturb_image(source: Path, output: Path, config: dict[str, object]) -> None:
    transform = config["image_transform"]
    with Image.open(source) as opened:
        rgb = opened.convert("RGB")
    hsv = rgb.convert("HSV")
    hue, saturation, value = hsv.split()
    rotation = int(transform["hue_rotation_uint8"])
    hue = hue.point([(index + rotation) % 256 for index in range(256)])
    shifted = Image.merge("HSV", (hue, saturation, value)).convert("RGB")
    padding = transform["padding_pixels"]
    width = shifted.width + int(padding["left"]) + int(padding["right"])
    height = shifted.height + int(padding["top"]) + int(padding["bottom"])
    canvas = Image.new("RGB", (width, height), tuple(transform["padding_rgb"]))
    canvas.paste(shifted, (int(padding["left"]), int(padding["top"])))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True, metadata={})
    os.utime(output, (946684800, 946684800))


def shuffled_order(case_ids: list[str], seed: int) -> list[dict[str, object]]:
    values = list(case_ids)
    random.Random(seed).shuffle(values)
    return [
        {"ordinal": ordinal, "CaseID": case_id}
        for ordinal, case_id in enumerate(values, start=1)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    args = parser.parse_args()
    base = args.base.resolve()
    config_path = base / "frozen" / "AMD2_STABILITY_CONFIG.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    claude_path = (
        base / "ai_codifiers" / "claude" / "CLAUDE_LABELS_98.csv"
    )
    codex_path = (
        base / "ai_codifiers" / "codex" / "CODEX_LABELS_98.csv"
    )
    claude = load_labels(claude_path, "CLAUDE")
    codex = load_labels(codex_path, "CODEX")
    if set(claude) != set(codex):
        raise ValueError("Claude and Codex CaseID sets differ")
    case_ids = sorted(claude)
    root = base / "amd2_stability"
    consensus_rows = [
        {
            "CaseID": case_id,
            "claude_label": claude[case_id],
            "codex_label": codex[case_id],
            "consensus_label": consensus_label(
                claude[case_id],
                codex[case_id],
            ),
            "information_status": "AI_CONSENSUS_NO_OUTCOME_AMD2",
        }
        for case_id in case_ids
    ]
    consensus_path = (
        root / "original_consensus" / "CLAUDE_CODEX_CONSENSUS_98.csv"
    )
    write_csv(
        consensus_path,
        [
            "CaseID",
            "claude_label",
            "codex_label",
            "consensus_label",
            "information_status",
        ],
        consensus_rows,
    )

    source_dir = base / "annotator_round1" / "renders"
    output_dir = root / "renders_perturbed"
    manifest_rows: list[dict[str, object]] = []
    for ordinal, case_id in enumerate(case_ids, start=1):
        source = source_dir / f"{case_id}.png"
        output = output_dir / f"{case_id}.png"
        if not source.exists():
            raise FileNotFoundError(source)
        perturb_image(source, output, config)
        with Image.open(source) as source_image:
            source_size = f"{source_image.width}x{source_image.height}"
        with Image.open(output) as output_image:
            output_size = f"{output_image.width}x{output_image.height}"
            metadata_clean = not bool(output_image.info)
        manifest_rows.append(
            {
                "ordinal": ordinal,
                "CaseID": case_id,
                "source_sha256": sha256_file(source),
                "output_sha256": sha256_file(output),
                "source_size": source_size,
                "output_size": output_size,
                "metadata_clean": metadata_clean,
                "information_change": "NONE_COSMETIC_ONLY",
            }
        )
    write_csv(
        root / "audit" / "PERTURBATION_MANIFEST_98.csv",
        [
            "ordinal",
            "CaseID",
            "source_sha256",
            "output_sha256",
            "source_size",
            "output_size",
            "metadata_clean",
            "information_change",
        ],
        manifest_rows,
    )
    write_csv(
        root / "orders" / "ORDER_CLAUDE_AMD2.csv",
        ["ordinal", "CaseID"],
        shuffled_order(case_ids, int(config["claude_order_seed"])),
    )
    write_csv(
        root / "orders" / "ORDER_CODEX_AMD2.csv",
        ["ordinal", "CaseID"],
        shuffled_order(case_ids, int(config["codex_order_seed"])),
    )
    counts = Counter(row["consensus_label"] for row in consensus_rows)
    receipt = {
        "protocol": config["protocol"],
        "outcome_loaded": False,
        "mapping_loaded": False,
        "cases": len(case_ids),
        "consensus_counts": dict(sorted(counts.items())),
        "original_ab_denominator": counts["A"] + counts["B"],
        "input_sha256": {
            "config": sha256_file(config_path),
            "claude": sha256_file(claude_path),
            "codex": sha256_file(codex_path),
        },
        "output_sha256": {
            "consensus": sha256_file(consensus_path),
            "manifest": sha256_file(
                root / "audit" / "PERTURBATION_MANIFEST_98.csv"
            ),
            "order_claude": sha256_file(
                root / "orders" / "ORDER_CLAUDE_AMD2.csv"
            ),
            "order_codex": sha256_file(
                root / "orders" / "ORDER_CODEX_AMD2.csv"
            ),
        },
        "all_metadata_clean": all(
            bool(row["metadata_clean"]) for row in manifest_rows
        ),
        "all_information_change_none": all(
            row["information_change"] == "NONE_COSMETIC_ONLY"
            for row in manifest_rows
        ),
    }
    receipt_path = root / "audit" / "AMD2_STABILITY_INPUT_RECEIPT.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
