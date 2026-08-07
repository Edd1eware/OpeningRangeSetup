from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FILES = (
    ROOT / "config" / "efficiency_v2_config.json",
    ROOT
    / "config"
    / "preregistration"
    / "EFFICIENCY_V2_PREREGISTRATION.md",
    ROOT
    / "config"
    / "preregistration"
    / "EFFICIENCY_AUDIT_FREEZE_MANIFEST.json",
    ROOT / "artifacts" / "efficiency_audit" / "result.json",
    ROOT / "artifacts" / "efficiency_audit" / "manifest.json",
)
OUTPUT = (
    ROOT
    / "config"
    / "preregistration"
    / "EFFICIENCY_V2_FREEZE_MANIFEST.json"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    manifest = {
        "definition_id": "VT_EFFICIENCY_DIAGNOSTIC_V2",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "DIAGNOSTIC_ONLY_BEFORE_REGIME_DISCOVERY",
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in FILES
        },
        "threshold": 0.65,
        "threshold_reduced": False,
        "discovery_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
    }
    OUTPUT.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
