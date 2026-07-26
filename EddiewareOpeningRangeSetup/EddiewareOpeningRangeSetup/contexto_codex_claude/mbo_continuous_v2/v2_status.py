"""Total V2 roadmap progress bar, derived from artifacts on disk.

Each milestone is detected by the existence (or content) of its frozen
artifact, so the bar reflects real state, not a guess.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BASE = Path(__file__).resolve().parent
CTX = BASE.parent
OUT = BASE / "output"
MH = BASE / "mH_source"


def stability_pass() -> bool:
    path = OUT / "V2_STABILITY_RESULT.json"
    if not path.exists():
        return False
    return json.loads(path.read_text()).get("JOINT_STABILITY") == "PASS"


def endpoint_done() -> bool:
    return (OUT / "V2_DISCOVERY_ENDPOINT_RESULT.json").exists()


MILESTONES = [
    ("V2-0  verificar estado congelado",
     lambda: (CTX / "20260725_035_CLAUDE_V2_0_VERIFICACION_ESTADO_CONGELADO.md"
              ).exists()),
    ("V2-1  preregistro convergente firmado",
     lambda: (BASE / "CODEX_COUNTERSIGN.md").exists()),
    ("V2-2  extractor 13 componentes sellado",
     lambda: (BASE / "V2_CODE_HASHES.sha256").exists()),
    ("V2-3  gate sintetico A1 + MIRROR",
     lambda: (BASE / "v2_synthetic_gate.py").exists() and stability_pass()),
    ("V2-4  estabilidad P1:P5 JOINT PASS", stability_pass),
    ("V2-5a bloqueo horizonte + costo estimado",
     lambda: (MH / "MH_COST_SUMMARY.json").exists()),
    ("V2-5b convergencia Codex fuente mH",
     lambda: (MH / "MH_SOURCE_ADDENDUM_SIGNED.md").exists()),
    ("V2-5c descarga MBP-1 +65s (98)",
     lambda: (MH / "MH_DOWNLOAD_RECEIPT.json").exists()),
    ("V2-5d construir Y_60 + cobertura >=56",
     lambda: (OUT / "V2_Y60_98.csv").exists()),
    ("V2-5e endpoint unico discovery", endpoint_done),
    ("V2-6  cierre (2024 CERRADO por FAIL discovery)",
     lambda: (CTX / "20260725_040_V2_CIERRE_DISCOVERY_FAIL.md").exists()
     or (OUT / "V2_VALIDATION_2024_RESULT.json").exists()),
]


def main() -> int:
    done = []
    for label, check in MILESTONES:
        try:
            done.append(bool(check()))
        except Exception:
            done.append(False)
    n = len(MILESTONES)
    k = sum(done)
    pct = 100.0 * k / n
    filled = int(round(pct / 10))
    bar = "█" * filled + "░" * (10 - filled)
    stamp = datetime.now().strftime("%H:%M:%S")
    current = next((label for label, ok in zip([m[0] for m in MILESTONES],
                                               done) if not ok), "COMPLETO")
    print(f"[{stamp}] V2 TOTAL {bar} {pct:5.1f}%  ({k}/{n})  ->  {current}",
          flush=True)
    if "--detail" in sys.argv:
        for (label, _), ok in zip(MILESTONES, done):
            print(f"   {'OK ' if ok else '.. '} {label}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
