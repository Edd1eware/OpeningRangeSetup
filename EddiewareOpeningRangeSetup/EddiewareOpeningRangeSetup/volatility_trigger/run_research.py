from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import traceback
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from atas_cache_decoder import load_cache_window  # noqa: E402
from telegram_run_summary_after_sync import send_persistent_text  # noqa: E402
from src.vt_core import (  # noqa: E402
    business_dates,
    build_session_candidates,
    causalize_trade_timestamps,
    load_config,
    session_bounds,
)
from src.vt_model import evaluate_discovery  # noqa: E402


CONFIG_PATH = ROOT / "config" / "discovery_config.json"
PREREG_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "VT_TIER1_PREREGISTRATION.md"
)
AMENDMENT_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "AMENDMENT_001_TIMESTAMP_AND_RUNTIME.md"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            allow_nan=False,
            default=json_default,
        ),
        encoding="utf-8",
    )


def telegram(config: dict, message: str, enabled: bool) -> bool:
    if not enabled:
        return False
    return send_persistent_text(
        config["telegram_results_folder"],
        message,
    )


def freeze() -> dict[str, object]:
    files = [
        CONFIG_PATH,
        PREREG_PATH,
        AMENDMENT_PATH,
        ROOT / "src" / "vt_core.py",
        ROOT / "src" / "vt_model.py",
        ROOT / "run_research.py",
    ]
    manifest = {
        "experiment_id": load_config(CONFIG_PATH)["experiment_id"],
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": load_config(CONFIG_PATH)["freeze_status"],
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        },
        "validation_opened": False,
        "holdout_opened": False,
        "visual_logic_modified": False,
    }
    write_json(ROOT / "config" / "preregistration" / "FREEZE_MANIFEST.json", manifest)
    return manifest


def stage_dates(stage: str, config: dict) -> list[date]:
    if stage == "smoke":
        return [date.fromisoformat(value) for value in config["splits"]["smoke"]]
    start, end = config["splits"][stage]
    return list(
        business_dates(
            date.fromisoformat(start),
            date.fromisoformat(end),
        )
    )


def predecessor_pass(stage: str) -> bool:
    predecessor = {
        "validation": "discovery",
        "holdout": "validation",
    }.get(stage)
    if predecessor is None:
        return True
    path = ROOT / "artifacts" / predecessor / "result.json"
    if not path.is_file():
        return False
    return bool(json.loads(path.read_text(encoding="utf-8")).get("pass"))


def load_session(
    session_date: date,
    cache_root: Path,
) -> tuple[object, np.ndarray, Path]:
    source_date = session_date - timedelta(days=1)
    source = cache_root / source_date.strftime("%Y_%m_%d") / "trades.dat"
    if not source.is_file() or source.stat().st_size <= 33:
        raise FileNotFoundError(f"missing trade cache: {source}")
    bounds = session_bounds(session_date)
    context, rows = load_cache_window(
        source,
        start_ticks=bounds["session_start"],
        end_ticks=bounds["load_end"],
    )
    return context, rows, source


def session_audit(
    session_date: date,
    context,
    rows: np.ndarray,
    source: Path,
    timestamp_qc: dict[str, float | int | str],
) -> dict[str, object]:
    if not math.isclose(context.tick_size, 0.25):
        raise ValueError(f"tick_size={context.tick_size}")
    if not math.isclose(context.lot_size, 1.0):
        raise ValueError(f"lot_size={context.lot_size}")
    if len(rows) == 0:
        raise ValueError("empty cash session")
    backward = int(np.sum(np.diff(rows["ticks"].astype(np.int64)) < 0))
    if backward:
        raise ValueError(f"nonmonotonic trade timestamps={backward}")
    invalid_sides = int(np.sum(rows["side_code"] > 2))
    if invalid_sides:
        raise ValueError(f"invalid trade sides={invalid_sides}")
    duplicate_mask = (
        (rows["ticks"][1:] == rows["ticks"][:-1])
        & (rows["side_code"][1:] == rows["side_code"][:-1])
        & (rows["price_raw"][1:] == rows["price_raw"][:-1])
        & (rows["volume_raw"][1:] == rows["volume_raw"][:-1])
    )
    return {
        "session_date": session_date.isoformat(),
        "source": str(source),
        "source_bytes": source.stat().st_size,
        "trade_rows": int(len(rows)),
        "first_ticks": int(rows[0]["ticks"]),
        "last_ticks": int(rows[-1]["ticks"]),
        "timestamp_backtracks": backward,
        **timestamp_qc,
        "adjacent_exact_duplicates": int(duplicate_mask.sum()),
        "tick_size": context.tick_size,
        "lot_size": context.lot_size,
        "status": "PASS",
    }


def run_data_stage(
    stage: str,
    config: dict,
    telegram_enabled: bool,
    limit: int | None = None,
) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    if not predecessor_pass(stage):
        raise RuntimeError(
            f"{stage} remains sealed because predecessor did not PASS"
        )
    output = ROOT / "artifacts" / stage
    per_session = output / "session_cache"
    per_session.mkdir(parents=True, exist_ok=True)
    cache_root = Path(config["cache_root"])
    dates = stage_dates(stage, config)
    if limit is not None:
        dates = dates[:limit]
    audits: list[dict] = []
    all_bursts: list[dict] = []
    candidate_parts: list[pd.DataFrame] = []

    telegram(
        config,
        (
            f"VT TIER1 | INICIO {stage.upper()}\n"
            f"Sesiones previstas: {len(dates)}\n"
            "Detector LB congelado; predictors <= t0; outcomes separados; "
            "sin PnL/TP/SL."
        ),
        telegram_enabled,
    )

    for ordinal, session_date in enumerate(dates, start=1):
        stem = session_date.isoformat()
        parquet_path = per_session / f"{stem}_candidates.parquet"
        bursts_path = per_session / f"{stem}_bursts.json"
        audit_path = per_session / f"{stem}_audit.json"
        if parquet_path.is_file() and bursts_path.is_file() and audit_path.is_file():
            part = pd.read_parquet(parquet_path)
            bursts = json.loads(bursts_path.read_text(encoding="utf-8"))
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        else:
            try:
                context, rows, source = load_session(session_date, cache_root)
                rows, timestamp_qc = causalize_trade_timestamps(
                    rows,
                    config["timestamp_qc"],
                )
                audit = session_audit(
                    session_date,
                    context,
                    rows,
                    source,
                    timestamp_qc,
                )
                burst_objects, part = build_session_candidates(
                    rows,
                    session_date,
                    config,
                )
                bursts = [asdict(value) for value in burst_objects]
                audit["liquidity_bursts"] = len(bursts)
                audit["candidate_rows"] = len(part)
                if not part.empty:
                    if int(part["causality_pass"].min()) != 1:
                        raise AssertionError("feature timestamp crossed t0")
                    part.to_parquet(parquet_path, index=False)
                else:
                    pd.DataFrame(
                        columns=[
                            "session_date",
                            "lb_id",
                            "sniper_success",
                        ]
                    ).to_parquet(parquet_path, index=False)
                write_json(bursts_path, bursts)
                write_json(audit_path, audit)
            except Exception as exc:
                audit = {
                    "session_date": session_date.isoformat(),
                    "status": "EXCLUDED",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
                part = pd.DataFrame()
                bursts = []
                write_json(audit_path, audit)
        audits.append(audit)
        all_bursts.extend(bursts)
        if not part.empty and "candidate_ticks" in part:
            candidate_parts.append(part)
        if ordinal % 10 == 0 or ordinal == len(dates):
            print(
                json.dumps(
                    {
                        "stage": stage,
                        "processed": ordinal,
                        "total": len(dates),
                        "bursts": len(all_bursts),
                        "candidate_rows": int(
                            sum(len(value) for value in candidate_parts)
                        ),
                    }
                ),
                flush=True,
            )

    candidates = (
        pd.concat(candidate_parts, ignore_index=True)
        if candidate_parts
        else pd.DataFrame()
    )
    pd.DataFrame(audits).to_csv(output / "data_audit.csv", index=False)
    pd.DataFrame(all_bursts).to_csv(output / "liquidity_bursts.csv", index=False)
    candidates.to_parquet(output / "vt_candidates.parquet", index=False)
    return candidates, audits, all_bursts


def smoke_result(
    candidates: pd.DataFrame,
    audits: list[dict],
    bursts: list[dict],
) -> dict[str, object]:
    valid_audits = [row for row in audits if row.get("status") == "PASS"]
    causal = (
        bool(len(candidates) and int(candidates["causality_pass"].min()) == 1)
    )
    outcome_columns = [
        value for value in candidates.columns if value.startswith(
            (
                "time_to_",
                "pre_expansion_",
                "initial_impulse_",
                "signed_displacement_",
                "directional_efficiency_",
                "sniper_success",
            )
        )
    ]
    feature_columns = [
        value
        for value in candidates.columns
        if value
        not in {
            *outcome_columns,
            "outcome_valid",
            "entry_price_raw",
        }
    ]
    leakage = sorted(set(outcome_columns) & set(feature_columns))
    pass_status = bool(
        len(valid_audits) == len(audits)
        and len(bursts) > 0
        and len(candidates) > 0
        and causal
        and not leakage
    )
    return {
        "stage": "smoke",
        "sessions": len(audits),
        "sessions_pass": len(valid_audits),
        "liquidity_bursts": len(bursts),
        "candidate_rows": len(candidates),
        "outcome_valid_rows": int(candidates.get("outcome_valid", pd.Series(dtype=int)).sum()),
        "sniper_success_rows": int(candidates.get("sniper_success", pd.Series(dtype=int)).sum()),
        "causality_pass": causal,
        "outcome_feature_intersection": leakage,
        "pass": pass_status,
        "validation_opened": False,
        "holdout_opened": False,
        "visual_logic_modified": False,
    }


def artifact_hashes(output: Path) -> dict[str, str]:
    names = [
        "data_audit.csv",
        "liquidity_bursts.csv",
        "vt_candidates.parquet",
        "result.json",
    ]
    return {
        name: sha256_file(output / name)
        for name in names
        if (output / name).is_file()
    }


def run(stage: str, telegram_enabled: bool, limit: int | None) -> dict:
    config = load_config(CONFIG_PATH)
    freeze_path = ROOT / "config" / "preregistration" / "FREEZE_MANIFEST.json"
    if not freeze_path.is_file():
        raise RuntimeError("run freeze before opening VT outcomes")
    candidates, audits, bursts = run_data_stage(
        stage,
        config,
        telegram_enabled,
        limit,
    )
    if stage == "smoke":
        result = smoke_result(candidates, audits, bursts)
    elif stage == "discovery":
        if candidates.empty:
            raise RuntimeError("discovery produced no candidates")
        result = evaluate_discovery(candidates, config)
        result.update(
            {
                "sessions_expected": len(audits),
                "sessions_pass": sum(
                    row.get("status") == "PASS" for row in audits
                ),
                "candidate_rows": len(candidates),
                "visual_logic_modified": False,
            }
        )
    else:
        raise NotImplementedError(
            f"{stage} runner remains sealed pending predecessor PASS"
        )
    output = ROOT / "artifacts" / stage
    write_json(output / "result.json", result)
    write_json(output / "manifest.json", artifact_hashes(output))

    if stage == "smoke":
        message = (
            "VT TIER1 | SMOKE RESULT\n"
            f"Sesiones {result['sessions_pass']}/{result['sessions']} | "
            f"LBs {result['liquidity_bursts']} | "
            f"candidatos {result['candidate_rows']}\n"
            f"Causalidad: {'PASS' if result['causality_pass'] else 'FAIL'} | "
            f"leakage feature/outcome: {len(result['outcome_feature_intersection'])}\n"
            f"VEREDICTO: {'PASS' if result['pass'] else 'FAIL'}"
        )
    else:
        metrics = result["candidate_metrics"]
        phenomenon = result["phenomenon"]
        message = (
            "VT TIER1 | DISCOVERY 2022 RESULT\n"
            f"LBs {phenomenon['liquidity_bursts']} | "
            f"LBs con trayectoria sniper {phenomenon['sniper_eligible_bursts']} "
            f"({phenomenon['sniper_eligible_rate']:.2%})\n"
            f"Familias KEEP: {', '.join(result['selected_families']) or 'NINGUNA'}\n"
            f"AUC {metrics['auc']:.4f} | IC95 "
            f"[{metrics['auc_ci95'][0]:.4f}, {metrics['auc_ci95'][1]:.4f}] | "
            f"PR-AUC {metrics['pr_auc']:.4f}\n"
            f"VEREDICTO: {'PASS' if result['pass'] else 'FAIL'} | "
            f"Validation 2023: {'AUTORIZADA' if result['pass'] else 'CERRADA'}"
        )
    telegram(config, message, telegram_enabled)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["freeze", "smoke", "discovery", "validation", "holdout"],
    )
    parser.add_argument("--telegram", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.command == "freeze":
        print(json.dumps(freeze(), indent=2))
        return 0
    try:
        result = run(args.command, args.telegram, args.limit)
        print(json.dumps(result, indent=2, default=json_default))
        return 0 if result.get("pass") else 2
    except Exception as exc:
        config = load_config(CONFIG_PATH)
        telegram(
            config,
            (
                f"VT TIER1 | {args.command.upper()} ERROR\n"
                f"{type(exc).__name__}: {exc}\n"
                "No se abrió el siguiente split."
            ),
            args.telegram,
        )
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
