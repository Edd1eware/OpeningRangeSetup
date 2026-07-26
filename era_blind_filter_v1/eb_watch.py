"""Live stage dashboard for EB-V1, redraws once per second."""

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

STAGES = [
    ("Preregistro congelado + hasheado",
     lambda: (BASE / "PREREG_HASH.sha256").exists()),
    ("Script del test sellado",
     lambda: (BASE / "CODE_HASH.sha256").exists()),
    ("Test ejecutado (disparo unico)",
     lambda: (OUT / "EB_RESULT.json").exists()),
    ("Tabla anio x metrica generada",
     lambda: (OUT / "EB_YEAR_TABLE.csv").exists()),
    ("Informe + Telegram enviado",
     lambda: (BASE / "TELEGRAM_SENT.flag").exists()),
]

# rough per-stage cost in seconds, for the ETA
COST = [2, 2, 25, 2, 15]


def verdict() -> str | None:
    path = OUT / "EB_RESULT.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text()).get("VERDICT")
    except Exception:
        return None


def render() -> str:
    done = []
    for _label, check in STAGES:
        try:
            done.append(bool(check()))
        except Exception:
            done.append(False)
    n, k = len(STAGES), sum(done)
    pct = 100.0 * k / n
    filled = int(round(BAR_W * pct / 100.0))
    bar = "█" * filled + "░" * (BAR_W - filled)
    remaining = sum(c for c, ok in zip(COST, done) if not ok)
    elapsed = timedelta(seconds=int(time.time() - START))
    stamp = datetime.now().strftime("%H:%M:%S")
    v = verdict()

    lines = [
        "",
        "  EB-V1 — FILTRO 3 CONDICIONES ERA-BLIND (OR breakout + trail 50/20/40)",
        "  " + "─" * 68,
        f"  {bar}  {pct:5.1f}%   {k}/{n} etapas",
        f"  reloj {stamp}    transcurrido {elapsed}    "
        f"restante aprox {remaining}s",
        "  " + "─" * 68,
        "",
    ]
    for (label, _), ok in zip(STAGES, done):
        mark = "\x1b[32m✔\x1b[0m" if ok else "\x1b[90m·\x1b[0m"
        text = label if ok else f"\x1b[1m{label}\x1b[0m"
        lines.append(f"   {mark}  {text}")
    lines += ["", "  " + "─" * 68]
    if v:
        color = "\x1b[32m" if v == "PASS" else "\x1b[31m"
        lines.append(f"  VEREDICTO: {color}{v}\x1b[0m")
    else:
        nxt = next((l for (l, _), ok in zip(STAGES, done) if not ok), None)
        lines.append(f"  EN CURSO: {nxt}" if nxt else "  COMPLETO")
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
