from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from atas_cache_decoder import load_cache_window  # noqa: E402
from telegram_run_summary_after_sync import send_persistent_text  # noqa: E402
from run_research import CONFIG_PATH, load_session, stage_dates  # noqa: E402
from src.efficiency_audit import (  # noqa: E402
    causal_depth_timestamps,
    reconstruct_quotes,
)
from src.post_lb_regime import (  # noqa: E402
    label_regime_path,
    reference_quote_at,
)
from src.vt_core import (  # noqa: E402
    NY,
    causalize_trade_timestamps,
    contiguous_trade_ticks,
    datetime_to_dotnet_ticks,
    detect_liquidity_bursts,
    load_config,
)


TARGET_CONFIG_PATH = ROOT / "config" / "post_lb_regime_v2_config.json"
TARGET_FREEZE_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "POST_LB_REGIME_V2_FREEZE_MANIFEST.json"
)
RUN_FREEZE_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "REGIME_DISCOVERY_TARGET_RUN_FREEZE_MANIFEST.json"
)
OUTPUT = ROOT / "artifacts" / "regime_discovery_target"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            allow_nan=False,
            default=lambda item: (
                int(item)
                if isinstance(item, np.integer)
                else float(item)
                if isinstance(item, np.floating)
                and math.isfinite(float(item))
                else None
            ),
        ),
        encoding="utf-8",
    )


def telegram(message: str, enabled: bool) -> bool:
    if not enabled:
        return False
    config = load_config(CONFIG_PATH)
    return send_persistent_text(
        config["telegram_results_folder"],
        message,
    )


def freeze() -> dict[str, object]:
    files = (
        TARGET_CONFIG_PATH,
        TARGET_FREEZE_PATH,
        Path(__file__).resolve(),
        ROOT / "src" / "post_lb_regime.py",
        ROOT / "src" / "efficiency_audit.py",
        ROOT / "src" / "vt_core.py",
        ROOT / "tests" / "test_post_lb_regime.py",
    )
    manifest = {
        "target_id": load_config(TARGET_CONFIG_PATH)["target_id"],
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BEFORE_DISCOVERY_TARGET_LABELS",
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        },
        "models_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
    }
    write_json(RUN_FREEZE_PATH, manifest)
    return manifest


def verify_freeze() -> dict[str, object]:
    if not RUN_FREEZE_PATH.is_file():
        raise RuntimeError("discovery target run is not frozen")
    manifest = json.loads(RUN_FREEZE_PATH.read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        observed = sha256_file(ROOT / relative)
        if observed != expected["sha256"]:
            raise RuntimeError(f"frozen file changed: {relative}")
    return manifest


def depth_bounds(session_date: date) -> tuple[int, int]:
    return (
        datetime_to_dotnet_ticks(
            datetime.combine(session_date, time(9, 25), tzinfo=NY)
        ),
        datetime_to_dotnet_ticks(
            datetime.combine(session_date, time(16, 0, 20), tzinfo=NY)
        ),
    )


def process_session(
    session_date: date,
    main_config: dict,
    target_config: dict,
) -> tuple[pd.DataFrame, dict[str, object]]:
    cache_root = Path(main_config["cache_root"])
    source_date = session_date - timedelta(days=1)
    source_dir = cache_root / source_date.strftime("%Y_%m_%d")
    depth_source = source_dir / "marketdepth.dat"
    if not depth_source.is_file() or depth_source.stat().st_size <= 25:
        raise FileNotFoundError(f"missing depth cache: {depth_source}")

    trade_context, raw_trades, trade_source = load_session(
        session_date,
        cache_root,
    )
    trades, trade_qc = causalize_trade_timestamps(
        raw_trades,
        main_config["timestamp_qc"],
    )
    trade_ticks = contiguous_trade_ticks(trades)
    bursts = detect_liquidity_bursts(
        trades,
        session_date,
        main_config["detector"],
    )
    if not bursts:
        return pd.DataFrame(), {
            "session_date": session_date.isoformat(),
            "trade_source": str(trade_source),
            "depth_source": str(depth_source),
            "liquidity_bursts": 0,
            "valid_reference_bursts": 0,
            "status": "NO_LB",
            **{f"trade_{key}": value for key, value in trade_qc.items()},
        }

    start_ticks, end_ticks = depth_bounds(session_date)
    depth_context, raw_depth = load_cache_window(
        depth_source,
        start_ticks=start_ticks,
        end_ticks=end_ticks,
    )
    if (
        not math.isclose(
            trade_context.tick_size,
            depth_context.tick_size,
        )
        or not math.isclose(
            trade_context.lot_size,
            depth_context.lot_size,
        )
    ):
        raise ValueError("trade/depth scale mismatch")
    depth, depth_ticks, depth_qc = causal_depth_timestamps(
        raw_depth,
        50.0,
    )
    quotes, quote_audit = reconstruct_quotes(
        depth,
        depth_ticks,
        {
            "min_spread_ticks": 1,
            "max_spread_ticks": 4,
        },
    )
    records: list[dict[str, object]] = []
    for burst in bursts:
        quote = reference_quote_at(
            quotes,
            depth_ticks,
            int(burst.publish_ticks),
            250.0,
        )
        if quote is None:
            continue
        outcome = label_regime_path(
            trade_ticks,
            trades["price_raw"].astype(np.int64),
            int(burst.publish_ticks),
            float(quote["mid_raw"]),
            int(burst.direction),
            int(target_config["threshold_ticks"]),
            int(target_config["horizon_ms"]),
            int(target_config["ambiguity_window_ms"]),
        )
        local_time = datetime.fromisoformat(
            burst.session_date
        )
        records.append(
            {
                **asdict(burst),
                "lb_mid_raw": float(quote["mid_raw"]),
                "lb_best_bid_raw": int(quote["best_bid_raw"]),
                "lb_best_ask_raw": int(quote["best_ask_raw"]),
                "lb_microprice_raw": float(
                    quote["microprice_raw"]
                ),
                "lb_quote_ticks": int(quote["quote_ticks"]),
                "lb_depth_age_ms": float(quote["depth_age_ms"]),
                "lb_quote_group_lag_ms": float(
                    quote["quote_group_lag_ms"]
                ),
                "month": session_date.strftime("%Y-%m"),
                "year": session_date.year,
                "hour_ny": (
                    (
                        datetime(1, 1, 1, tzinfo=timezone.utc)
                        + timedelta(
                            seconds=int(burst.publish_ticks)
                            // 10_000_000,
                            microseconds=(
                                int(burst.publish_ticks) % 10_000_000
                            )
                            // 10,
                        )
                    )
                    .astimezone(NY)
                    .hour
                ),
                **outcome,
            }
        )
    return pd.DataFrame(records), {
        "session_date": session_date.isoformat(),
        "trade_source": str(trade_source),
        "depth_source": str(depth_source),
        "liquidity_bursts": len(bursts),
        "valid_reference_bursts": len(records),
        "reference_coverage": len(records) / max(len(bursts), 1),
        "status": "PASS",
        **{f"trade_{key}": value for key, value in trade_qc.items()},
        **{f"depth_{key}": value for key, value in depth_qc.items()},
        **quote_audit,
    }


def target_gates(
    labels: pd.DataFrame,
    audits: pd.DataFrame,
    config: dict,
) -> tuple[pd.DataFrame, dict[str, object]]:
    gates = config["target_only_discovery_gates"]
    resolved_classes = list(config["resolved_classes"])
    resolved = labels[labels["regime"].isin(resolved_classes)]
    counts = resolved["regime"].value_counts()
    shares = counts / max(len(resolved), 1)
    month_counts = pd.crosstab(
        resolved["month"],
        resolved["regime"],
    ).reindex(columns=resolved_classes, fill_value=0)
    minimum_count = min(
        int(counts.get(regime, 0)) for regime in resolved_classes
    )
    minimum_months = min(
        int((month_counts[regime] > 0).sum())
        for regime in resolved_classes
    )
    maximum_share = max(
        float(shares.get(regime, 0.0))
        for regime in resolved_classes
    )
    maximum_month_concentration = max(
        float(
            month_counts[regime].max()
            / max(month_counts[regime].sum(), 1)
        )
        for regime in resolved_classes
    )
    side_counts = pd.crosstab(
        resolved["side"],
        resolved["regime"],
    ).reindex(columns=resolved_classes, fill_value=0)
    side_probabilities = side_counts.div(
        side_counts.sum(axis=1),
        axis=0,
    )
    side_tvd = float(
        0.5
        * np.abs(
            side_probabilities.loc["BUY"]
            - side_probabilities.loc["SELL"]
        ).sum()
    )
    ambiguous_share = float(
        labels["regime"].eq(config["abstention_class"]).mean()
    )
    depth_sessions = audits[
        audits["status"].isin(["PASS", "NO_LB"])
    ]
    total_bursts = int(depth_sessions["liquidity_bursts"].sum())
    valid_bursts = int(
        depth_sessions["valid_reference_bursts"].sum()
    )
    reference_coverage = valid_bursts / max(total_bursts, 1)
    checks = {
        "valid_lb_pass": len(labels)
        >= int(gates["min_valid_liquidity_bursts"]),
        "class_count_pass": minimum_count
        >= int(gates["min_each_resolved_class"]),
        "month_presence_pass": minimum_months
        >= int(gates["min_months_each_resolved_class"]),
        "degeneracy_pass": maximum_share
        <= float(gates["max_single_resolved_class_share"]),
        "side_symmetry_pass": side_tvd
        <= float(gates["max_buy_sell_total_variation"]),
        "month_concentration_pass": maximum_month_concentration
        <= float(
            gates["max_month_concentration_each_resolved_class"]
        ),
        "ambiguous_share_pass": ambiguous_share
        <= float(gates["max_ambiguous_share"]),
        "reference_coverage_pass": reference_coverage
        >= float(gates["min_reference_coverage_in_depth_sessions"]),
    }
    metrics = {
        "valid_liquidity_bursts": len(labels),
        "resolved_liquidity_bursts": len(resolved),
        "minimum_resolved_class_count": minimum_count,
        "minimum_months_each_resolved_class": minimum_months,
        "maximum_resolved_class_share": maximum_share,
        "buy_sell_total_variation": side_tvd,
        "maximum_month_concentration": maximum_month_concentration,
        "ambiguous_share": ambiguous_share,
        "reference_coverage_in_depth_sessions": reference_coverage,
        **checks,
        "pass": all(checks.values()),
    }
    distribution = (
        labels.groupby(["month", "side", "regime"], dropna=False)
        .size()
        .rename("count")
        .reset_index()
    )
    return distribution, metrics


def run(telegram_enabled: bool) -> dict[str, object]:
    freeze_manifest = verify_freeze()
    main_config = load_config(CONFIG_PATH)
    target_config = load_config(TARGET_CONFIG_PATH)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cache_dir = OUTPUT / "session_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    dates = stage_dates("discovery", main_config)
    telegram(
        "POST-LB REGIME V2 | INICIO DISCOVERY TARGET-ONLY\n"
        f"Fechas previstas: {len(dates)}. 8t/5s/MID; AMBIGUOUS=abstencion. "
        "Sin features/modelos/AUC/PnL.",
        telegram_enabled,
    )
    parts: list[pd.DataFrame] = []
    audits: list[dict[str, object]] = []
    for ordinal, session_date in enumerate(dates, start=1):
        stem = session_date.isoformat()
        label_path = cache_dir / f"{stem}_labels.parquet"
        audit_path = cache_dir / f"{stem}_audit.json"
        if label_path.is_file() and audit_path.is_file():
            part = pd.read_parquet(label_path)
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        else:
            try:
                part, audit = process_session(
                    session_date,
                    main_config,
                    target_config,
                )
                part.to_parquet(label_path, index=False)
            except Exception as exc:
                part = pd.DataFrame()
                audit = {
                    "session_date": stem,
                    "liquidity_bursts": 0,
                    "valid_reference_bursts": 0,
                    "status": "EXCLUDED",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            write_json(audit_path, audit)
        if not part.empty:
            parts.append(part)
        audits.append(audit)
        if ordinal % 20 == 0 or ordinal == len(dates):
            labels_so_far = sum(len(value) for value in parts)
            progress = (
                "POST-LB REGIME V2 | PROGRESO TARGET-ONLY\n"
                f"{ordinal}/{len(dates)} sesiones; "
                f"{labels_so_far} LB validos."
            )
            print(
                json.dumps(
                    {
                        "processed": ordinal,
                        "total": len(dates),
                        "valid_lbs": labels_so_far,
                    }
                ),
                flush=True,
            )
            if ordinal % 60 == 0 or ordinal == len(dates):
                telegram(progress, telegram_enabled)
    labels = (
        pd.concat(parts, ignore_index=True)
        if parts
        else pd.DataFrame()
    )
    audit_frame = pd.DataFrame(audits)
    distribution, metrics = target_gates(
        labels,
        audit_frame,
        target_config,
    )
    result = {
        "target_id": target_config["target_id"],
        "status": (
            "REGIME_V2_TARGET_DISCOVERY_PASS"
            if metrics["pass"]
            else "REGIME_V2_TARGET_DISCOVERY_FAIL"
        ),
        "threshold_ticks": int(target_config["threshold_ticks"]),
        "horizon_ms": int(target_config["horizon_ms"]),
        "ambiguous_policy": target_config["ambiguous_policy"],
        **metrics,
        "models_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "run_freeze_sha256": sha256_file(RUN_FREEZE_PATH),
        "input_freeze_status": freeze_manifest["status"],
    }
    labels.to_parquet(OUTPUT / "regime_discovery_labels.parquet", index=False)
    audit_frame.to_csv(OUTPUT / "data_audit.csv", index=False)
    distribution.to_csv(
        OUTPUT / "regime_distribution.csv",
        index=False,
    )
    write_json(OUTPUT / "result.json", result)
    artifact_names = (
        "regime_discovery_labels.parquet",
        "data_audit.csv",
        "regime_distribution.csv",
        "result.json",
    )
    write_json(
        OUTPUT / "manifest.json",
        {
            name: sha256_file(OUTPUT / name)
            for name in artifact_names
        },
    )
    telegram(
        (
            "POST-LB REGIME V2 | RESULTADO DISCOVERY TARGET-ONLY\n"
            f"Estado: {result['status']}\n"
            f"LB validos: {result['valid_liquidity_bursts']}; "
            f"min clase: {result['minimum_resolved_class_count']}; "
            f"meses min: {result['minimum_months_each_resolved_class']}\n"
            f"TVD BUY/SELL: {result['buy_sell_total_variation']:.3f}; "
            f"AMBIGUOUS: {result['ambiguous_share']:.3f}\n"
            "Modelos aun cerrados."
        ),
        telegram_enabled,
    )
    print(json.dumps(result, indent=2), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("freeze")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--telegram", action="store_true")
    arguments = parser.parse_args()
    if arguments.command == "freeze":
        print(json.dumps(freeze(), indent=2))
        return 0
    run(arguments.telegram)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
