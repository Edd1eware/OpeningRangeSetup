"""Render the V4/V5 instrument result for the persistent Telegram report."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def main() -> None:
    project = Path(__file__).resolve().parent
    output = (
        project
        / "contexto_codex_claude"
        / "joint_ab_v5"
        / "AB_V4_V5_INSTRUMENT_RESULT.png"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    labels = ["A Absorción", "B Breakout", "C Variable"]
    v4 = np.array([0, 0, 98])
    v5 = np.array([12, 9, 77])
    x = np.arange(len(labels))
    width = 0.34
    fig, axes = plt.subplots(
        1, 2, figsize=(11.5, 5.3), gridspec_kw={"width_ratios": [1.2, 1]}
    )
    axes[0].bar(x - width / 2, v4, width, label="V4", color="#64748b")
    axes[0].bar(x + width / 2, v5, width, label="V5", color="#0f766e")
    axes[0].axhline(15, color="#dc2626", linestyle="--", linewidth=1.4)
    axes[0].text(2.08, 16.5, "mínimo 15 sesiones", color="#b91c1c")
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("Sesiones (n=98)")
    axes[0].set_title("Prevalencia del instrumento")
    axes[0].legend()
    for index, value in enumerate(v5):
        axes[0].text(index + width / 2, value + 1.5, str(value), ha="center")

    names = ["A · 0.85", "A · 1.15", "B · 0.85", "B · 1.15"]
    values = [0.923, 0.417, 0.563, 0.667]
    colors = ["#16a34a" if value >= 0.70 else "#dc2626" for value in values]
    axes[1].barh(names, values, color=colors)
    axes[1].axvline(0.70, color="#111827", linestyle="--", linewidth=1.4)
    axes[1].set_xlim(0, 1)
    axes[1].set_xlabel("Jaccard")
    axes[1].set_title("Estabilidad V5 (gate ≥ 0.70)")
    for index, value in enumerate(values):
        axes[1].text(value + 0.02, index, f"{value:.3f}", va="center")

    fig.suptitle(
        "Liquidity Burst — taxonomía de precio 5 s: V4 y V5 FAIL",
        fontsize=14,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.01,
        "No se entrenó ningún modelo. Próximo enfoque: estado mecánico del libro.",
        ha="center",
        color="#334155",
    )
    fig.tight_layout(rect=[0, 0.04, 1, 0.93])
    fig.savefig(output, dpi=180, bbox_inches="tight")
    print(output)


if __name__ == "__main__":
    main()
