"""Live V2 roadmap dashboard: full-screen redraw once per second.

Run in its own console window. Reads real artifacts from disk, so the bar
reflects actual state. Ctrl+C to quit.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta

from v2_status import MILESTONES

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

os.system("")  # enable ANSI on Windows terminals

BAR_W = 30
START = time.time()


def render() -> str:
    done = []
    for _label, check in MILESTONES:
        try:
            done.append(bool(check()))
        except Exception:
            done.append(False)
    n = len(MILESTONES)
    k = sum(done)
    pct = 100.0 * k / n
    filled = int(round(BAR_W * pct / 100.0))
    bar = "█" * filled + "░" * (BAR_W - filled)
    elapsed = timedelta(seconds=int(time.time() - START))
    stamp = datetime.now().strftime("%H:%M:%S")

    lines = [
        "",
        "  LIQUIDITY BURST — ROADMAP V2 (score continuo defensa/aceptacion)",
        "  " + "─" * 62,
        f"  {bar}  {pct:5.1f}%   {k}/{n} hitos",
        f"  reloj {stamp}     en pantalla {elapsed}",
        "  " + "─" * 62,
        "",
    ]
    for (label, _), ok in zip(MILESTONES, done):
        mark = "\x1b[32m✔\x1b[0m" if ok else "\x1b[90m·\x1b[0m"
        text = label if ok else f"\x1b[1m{label}\x1b[0m"
        lines.append(f"   {mark}  {text}")
    nxt = next((lbl for (lbl, _), ok in zip(MILESTONES, done) if not ok), None)
    lines += [
        "",
        "  " + "─" * 62,
        f"  EN CURSO: {nxt}" if nxt else "  ROADMAP COMPLETO",
        "  (Ctrl+C para cerrar esta ventana)",
    ]
    return "\n".join(lines)


def main() -> int:
    try:
        while True:
            sys.stdout.write("\x1b[2J\x1b[H")   # clear + home
            sys.stdout.write(render())
            sys.stdout.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
