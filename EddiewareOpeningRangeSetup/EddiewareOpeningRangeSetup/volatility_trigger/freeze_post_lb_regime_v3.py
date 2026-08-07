from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy
import pandas
import pyarrow


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "post_lb_regime_v3_config.json"
PREREG = (
    ROOT
    / "config"
    / "preregistration"
    / "POST_LB_REGIME_V3_PREREGISTRATION.md"
)
OUTPUT = (
    ROOT
    / "config"
    / "preregistration"
    / "POST_LB_REGIME_V3_FREEZE_MANIFEST.json"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> int:
    files = (
        CONFIG,
        PREREG,
        ROOT
        / "config"
        / "preregistration"
        / "CLAUDE_CODEX_CONSENSUS_DATA_INTEGRITY.md",
        ROOT
        / "config"
        / "preregistration"
        / "AMENDMENT_002_AMBIGUOUS_AS_ABSTENTION.md",
        ROOT
        / "config"
        / "preregistration"
        / "AMENDMENT_003_CURRENT_QUOTE_VALIDITY.md",
        ROOT
        / "config"
        / "preregistration"
        / "AMENDMENT_003_PRE_FIX_MANIFEST.json",
        ROOT
        / "config"
        / "preregistration"
        / "ERRATA_001_MISSING_REFERENCE_ARTIFACT.md",
        ROOT
        / "config"
        / "preregistration"
        / "ERRATA_SCOPE_A1_EQUIVALENCE.md",
        ROOT
        / "config"
        / "preregistration"
        / "POST_LB_REGIME_AUDIT_INTEGRITY_V3_FREEZE_MANIFEST.json",
        ROOT
        / "artifacts"
        / "post_lb_regime_audit_integrity_v3"
        / "manifest.json",
        ROOT
        / "artifacts"
        / "resolved_threshold_audit_v3"
        / "manifest.json",
        ROOT / "artifacts" / "data_coverage" / "manifest.json",
        ROOT
        / "artifacts"
        / "data_coverage"
        / "depth_coverage_manifest.csv",
        ROOT / "src" / "post_lb_regime.py",
        ROOT / "src" / "efficiency_audit.py",
        ROOT / "tests" / "test_post_lb_regime.py",
        ROOT / "tests" / "test_efficiency_audit.py",
        Path(__file__).resolve(),
    )
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    manifest = {
        "target_id": config["target_id"],
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BEFORE_V3_DISCOVERY_TARGET_LABELS",
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        },
        "runtime": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "numpy": numpy.__version__,
            "pandas": pandas.__version__,
            "pyarrow": pyarrow.__version__,
        },
        "threshold_ticks": 16,
        "horizon_ms": 5000,
        "ambiguity_window_ms": 250,
        "current_quote_required": True,
        "hierarchy_consumed": True,
        "ambiguous_merged": False,
        "non_smoke_v3_labels_opened": False,
        "features_opened": False,
        "models_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "git_status": "UNTRACKED_USER_AUTHORIZATION_REQUIRED",
    }
    OUTPUT.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))
    print(
        json.dumps(
            {
                "v3_prereg_sha256": sha256_file(PREREG),
                "v3_config_sha256": sha256_file(CONFIG),
                "v3_freeze_sha256": sha256_file(OUTPUT),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
