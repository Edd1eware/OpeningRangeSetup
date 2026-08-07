from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FILES = (
    ROOT / "config" / "post_lb_regime_v2_config.json",
    ROOT
    / "config"
    / "preregistration"
    / "POST_LB_REGIME_V2_PREREGISTRATION.md",
    ROOT
    / "config"
    / "preregistration"
    / "POST_LB_REGIME_AUDIT_FREEZE_MANIFEST.json",
    ROOT / "artifacts" / "post_lb_regime_audit" / "result.json",
    ROOT / "artifacts" / "post_lb_regime_audit" / "manifest.json",
)
OUTPUT = (
    ROOT
    / "config"
    / "preregistration"
    / "POST_LB_REGIME_V2_FREEZE_MANIFEST.json"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    manifest = {
        "target_id": "POST_LB_REGIME_V2_RESOLVED_WITH_ABSTENTION",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BEFORE_DISCOVERY_REGIME_LABELS",
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in FILES
        },
        "threshold_ticks": 8,
        "horizon_ms": 5000,
        "ambiguity_window_ms": 250,
        "ambiguous_merged": False,
        "discovery_models_opened": False,
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
