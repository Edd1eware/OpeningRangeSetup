"""Build AMD-3 stable core and second cosmetic perturbation without outcomes."""

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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def stable_core(original: str, perturbation1: str) -> str:
    if original == perturbation1 and original in {"A", "B"}:
        return original
    return "C"


def perturb_image(source: Path, output: Path, config: dict[str, object]) -> None:
    transform = config["image_transform"]
    with Image.open(source) as opened:
        rgb = opened.convert("RGB")
    hue, saturation, value = rgb.convert("HSV").split()
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
    root = base / "amd3_stability"
    config_path = base / "frozen" / "AMD3_STABILITY_CONFIG.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    amd2_cases_path = (
        base / "amd2_stability" / "audit" / "AMD2_STABILITY_CASES_98.csv"
    )
    amd2_rows = read_csv(amd2_cases_path)
    if len(amd2_rows) != 98:
        raise ValueError("AMD2 stability cases must contain 98 rows")
    stable_rows = []
    for row in sorted(amd2_rows, key=lambda item: item["CaseID"]):
        label = stable_core(
            row["original_consensus"].strip().upper(),
            row["new_consensus"].strip().upper(),
        )
        stable_rows.append(
            {
                "CaseID": row["CaseID"],
                "original_consensus": row["original_consensus"],
                "perturbation1_consensus": row["new_consensus"],
                "amd3_stable_core": label,
                "information_status": "AMD3_STABLE_CORE_NO_OUTCOME",
            }
        )
    stable_path = root / "stable_core" / "AMD3_STABLE_CORE_98.csv"
    write_csv(
        stable_path,
        [
            "CaseID",
            "original_consensus",
            "perturbation1_consensus",
            "amd3_stable_core",
            "information_status",
        ],
        stable_rows,
    )
    case_ids = [row["CaseID"] for row in stable_rows]
    source_dir = base / "annotator_round1" / "renders"
    output_dir = root / "renders_perturbed2"
    manifest_rows = []
    for ordinal, case_id in enumerate(case_ids, start=1):
        source = source_dir / f"{case_id}.png"
        output = output_dir / f"{case_id}.png"
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
    manifest_path = root / "audit" / "PERTURBATION2_MANIFEST_98.csv"
    write_csv(
        manifest_path,
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
    claude_order = root / "orders" / "ORDER_CLAUDE_AMD3.csv"
    codex_order = root / "orders" / "ORDER_CODEX_AMD3.csv"
    write_csv(
        claude_order,
        ["ordinal", "CaseID"],
        shuffled_order(case_ids, int(config["claude_order_seed"])),
    )
    write_csv(
        codex_order,
        ["ordinal", "CaseID"],
        shuffled_order(case_ids, int(config["codex_order_seed"])),
    )
    counts = Counter(row["amd3_stable_core"] for row in stable_rows)
    receipt = {
        "protocol": config["protocol"],
        "outcome_loaded": False,
        "mapping_loaded": False,
        "cases": len(stable_rows),
        "stable_core_counts": dict(sorted(counts.items())),
        "primary_denominator": counts["A"] + counts["B"],
        "input_sha256": {
            "config": sha256_file(config_path),
            "amd2_cases": sha256_file(amd2_cases_path),
        },
        "output_sha256": {
            "stable_core": sha256_file(stable_path),
            "manifest": sha256_file(manifest_path),
            "order_claude": sha256_file(claude_order),
            "order_codex": sha256_file(codex_order),
        },
        "all_metadata_clean": all(
            bool(row["metadata_clean"]) for row in manifest_rows
        ),
        "all_information_change_none": all(
            row["information_change"] == "NONE_COSMETIC_ONLY"
            for row in manifest_rows
        ),
    }
    receipt_path = root / "audit" / "AMD3_STABILITY_INPUT_RECEIPT.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
