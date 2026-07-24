"""Telegram status for the MATRIX + MBO discovery pilot."""

from __future__ import annotations

import argparse
from pathlib import Path

from lb_matrix_classification_monitor import calculate


STATUS_FILE = "telegram_lb_hypothesis.txt"


def format_status(values: dict[str, object]) -> str:
    causal = values.get("causal_pct")
    causal_text = "CALCULANDO" if causal is None else f"{float(causal):.1f}% causal"
    return (
        "MATRIX + MBO CLASSIFICATION TEST : "
        f"{int(values.get('bursts', 0))} bursts post-LB | "
        f"{int(values.get('events', 0))} eventos | {causal_text} | "
        f"{int(values.get('sessions', 0))} sesiones | "
        "Combinaciones: PENDIENTE HASTA COMPLETAR DISCOVERY"
    )


def update_status_file(results_folder: Path | str) -> str:
    root = Path(results_folder)
    root.mkdir(parents=True, exist_ok=True)
    status = format_status(calculate(root))
    (root / STATUS_FILE).write_text(status + "\n", encoding="utf-8")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_folder", type=Path)
    args = parser.parse_args()
    print(update_status_file(args.results_folder))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
