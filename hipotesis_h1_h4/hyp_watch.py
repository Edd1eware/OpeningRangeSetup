"""Live dashboard for the H1..H4 hypothesis battery."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass
os.system("")

BASE = Path(__file__).resolve().parent
OUT = BASE / "output"
BAR_W = 34
START = time.time()

HYP = [
    ("H1", "Sesgo estructural UP (0 parametros libres)", 60),
    ("H2", "Gate de regimen tendencial K=20", 90),
    ("H4", "Sizing dinamico kill-switch + MC Lucid", 240),
    ("H3", "Liquidity Burst como filtro de dia", 120),
]


def status(tag: str):
    path = OUT / f"{tag}_RESULT.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text()).get("VERDICT")
    except Exception:
        return None


def render() -> str:
    states = [status(t) for t, _, _ in HYP]
    done = sum(1 for s in states if s is not None)
    n = len(HYP)
    pct = 100.0 * done / n
    filled = int(round(BAR_W * pct / 100.0))
    bar = "█" * filled + "░" * (BAR_W - filled)
    remaining = sum(c for (_t, _d, c), s in zip(HYP, states) if s is None)
    elapsed = timedelta(seconds=int(time.time() - START))
    stamp = datetime.now().strftime("%H:%M:%S")

    lines = [
        "",
        "  BATERIA DE HIPOTESIS H1..H4 — busqueda de edge (era-blind)",
        "  " + "─" * 68,
        f"  {bar}  {pct:5.1f}%   {done}/{n} hipotesis resueltas",
        f"  reloj {stamp}    transcurrido {elapsed}    "
        f"restante aprox {remaining//60}m {remaining%60}s",
        "  " + "─" * 68,
        "",
    ]
    for (tag, desc, _c), s in zip(HYP, states):
        if s == "PASS":
            mark, txt = "\x1b[32m✔\x1b[0m", f"\x1b[32m{tag} CANDIDATA\x1b[0m"
        elif s == "FAIL":
            mark, txt = "\x1b[31m✘\x1b[0m", f"\x1b[31m{tag} rechazada\x1b[0m"
        elif s is not None:
            mark, txt = "\x1b[33m?\x1b[0m", f"\x1b[33m{tag} {s}\x1b[0m"
        else:
            mark, txt = "\x1b[90m·\x1b[0m", f"{tag} pendiente"
        lines.append(f"   {mark}  {txt:28s} {desc}")

    lines += ["", "  " + "─" * 68]
    nxt = next((f"{t} — {d}" for (t, d, _c), s in zip(HYP, states)
                if s is None), None)
    lines.append(f"  EN CURSO: {nxt}" if nxt else "  BATERIA COMPLETA")
    lines.append("  (Ctrl+C para cerrar)")
    return "\n".join(lines)


def main() -> int:
    try:
        while True:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.write(render())
            sys.stdout.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
