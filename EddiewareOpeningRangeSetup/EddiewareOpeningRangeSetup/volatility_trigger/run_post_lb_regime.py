from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
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
from run_research import CONFIG_PATH, load_session  # noqa: E402
from src.efficiency_audit import (  # noqa: E402
    causal_depth_timestamps,
    reconstruct_quotes,
)
from src.post_lb_regime import (  # noqa: E402
    REGIME_CLASSES,
    label_regime_path,
    reference_prices,
    reference_quote_at,
)
from src.vt_core import (  # noqa: E402
    NY,
    causalize_trade_timestamps,
    contiguous_trade_ticks,
    datetime_to_dotnet_ticks,
    dotnet_ticks_to_datetime,
    load_config,
)


REGIME_CONFIG_PATH = ROOT / "config" / "post_lb_regime_config.json"
REGIME_PREREG_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "POST_LB_REGIME_PREREGISTRATION.md"
)
REGIME_SOURCE_PATH = ROOT / "src" / "post_lb_regime.py"
REGIME_TEST_PATH = ROOT / "tests" / "test_post_lb_regime.py"
SYNTHETIC_REPORT_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "SYNTHETIC_REGIME_TESTS.md"
)
FREEZE_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "POST_LB_REGIME_AUDIT_FREEZE_MANIFEST.json"
)
OUTPUT = ROOT / "artifacts" / "post_lb_regime_audit"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def json_default(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
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


def telegram(message: str, enabled: bool) -> bool:
    if not enabled:
        return False
    config = load_config(CONFIG_PATH)
    return send_persistent_text(
        config["telegram_results_folder"],
        message,
    )


def freeze() -> dict[str, object]:
    config_hash = sha256_file(REGIME_CONFIG_PATH)
    (
        REGIME_CONFIG_PATH.parent
        / "post_lb_regime_config.sha256"
    ).write_text(
        f"{config_hash}  post_lb_regime_config.json\n",
        encoding="utf-8",
    )
    files = (
        REGIME_CONFIG_PATH,
        REGIME_CONFIG_PATH.parent / "post_lb_regime_config.sha256",
        REGIME_PREREG_PATH,
        REGIME_SOURCE_PATH,
        Path(__file__).resolve(),
        REGIME_TEST_PATH,
        SYNTHETIC_REPORT_PATH,
        ROOT / "src" / "efficiency_audit.py",
        ROOT / "config" / "preregistration" / "FREEZE_MANIFEST.json",
        ROOT
        / "config"
        / "preregistration"
        / "EFFICIENCY_V2_FREEZE_MANIFEST.json",
        ROOT / "artifacts" / "smoke" / "manifest.json",
        ROOT / "artifacts" / "smoke" / "liquidity_bursts.csv",
    )
    manifest = {
        "audit_id": load_config(REGIME_CONFIG_PATH)["audit_id"],
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BEFORE_REAL_REGIME_LABELS",
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        },
        "discovery_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
    }
    write_json(FREEZE_PATH, manifest)
    return manifest


def verify_freeze() -> dict[str, object]:
    if not FREEZE_PATH.is_file():
        raise RuntimeError("post-LB regime audit is not frozen")
    manifest = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        observed = sha256_file(ROOT / relative)
        if observed != expected["sha256"]:
            raise RuntimeError(
                f"frozen file changed: {relative}: "
                f"{observed}!={expected['sha256']}"
            )
    return manifest


def depth_bounds(session_date: date, config: dict) -> tuple[int, int]:
    start = time.fromisoformat(config["depth_warmup_start_ny"])
    end = time.fromisoformat(config["depth_end_ny"])
    return (
        datetime_to_dotnet_ticks(
            datetime.combine(session_date, start, tzinfo=NY)
        ),
        datetime_to_dotnet_ticks(
            datetime.combine(session_date, end, tzinfo=NY)
        ),
    )


def _label_record(
    burst,
    reference_name: str,
    reference_price: float,
    threshold: int,
    horizon: int,
    ambiguity: int,
    trade_ticks: np.ndarray,
    trade_prices: np.ndarray,
    quote: dict[str, float | int],
) -> dict[str, object]:
    outcome = label_regime_path(
        trade_ticks,
        trade_prices,
        int(burst.publish_ticks),
        reference_price,
        int(burst.direction),
        threshold,
        horizon,
        ambiguity,
    )
    local_time = dotnet_ticks_to_datetime(
        int(burst.publish_ticks)
    ).astimezone(NY)
    return {
        "lb_id": burst.lb_id,
        "session_date": burst.session_date,
        "lb_publish_ticks": int(burst.publish_ticks),
        "lb_side": burst.side,
        "lb_direction": int(burst.direction),
        "lb_last_trade_raw": int(burst.price_raw),
        "lb_mid_raw": float(quote["mid_raw"]),
        "lb_best_bid_raw": int(quote["best_bid_raw"]),
        "lb_best_ask_raw": int(quote["best_ask_raw"]),
        "lb_microprice_raw": float(quote["microprice_raw"]),
        "lb_quote_ticks": int(quote["quote_ticks"]),
        "lb_depth_age_ms": float(quote["depth_age_ms"]),
        "lb_quote_group_lag_ms": float(
            quote["quote_group_lag_ms"]
        ),
        "reference": reference_name,
        "reference_price_raw": reference_price,
        "threshold_ticks": threshold,
        "horizon_ms": horizon,
        "ambiguity_window_ms": ambiguity,
        "year": local_time.year,
        "month": local_time.strftime("%Y-%m"),
        "hour_ny": local_time.hour,
        **outcome,
    }


def build_labels(
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    main_config = load_config(CONFIG_PATH)
    cache_root = Path(main_config["cache_root"])
    bursts = pd.read_csv(
        ROOT / "artifacts" / "smoke" / "liquidity_bursts.csv"
    )
    labels: list[dict[str, object]] = []
    sensitivity: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []

    for ordinal, (session_value, burst_part) in enumerate(
        bursts.groupby("session_date", sort=True),
        start=1,
    ):
        session_date = date.fromisoformat(str(session_value))
        trade_context, raw_trades, trade_source = load_session(
            session_date,
            cache_root,
        )
        trades, trade_qc = causalize_trade_timestamps(
            raw_trades,
            main_config["timestamp_qc"],
        )
        trade_ticks = contiguous_trade_ticks(trades)
        trade_prices = trades["price_raw"].astype(np.int64)

        source_date = session_date - timedelta(days=1)
        depth_source = (
            cache_root
            / source_date.strftime("%Y_%m_%d")
            / "marketdepth.dat"
        )
        start_ticks, end_ticks = depth_bounds(session_date, config)
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
            raise ValueError(f"trade/depth scale mismatch: {session_value}")
        depth, depth_ticks, depth_qc = causal_depth_timestamps(
            raw_depth,
            float(
                config["depth_timestamp_policy"]["max_jitter_ms"]
            ),
        )
        quotes, quote_audit = reconstruct_quotes(
            depth,
            depth_ticks,
            config["quote_policy"],
        )
        valid_bursts = 0
        for burst in burst_part.itertuples(index=False):
            quote = reference_quote_at(
                quotes,
                depth_ticks,
                int(burst.publish_ticks),
                float(config["quote_policy"]["max_reference_age_ms"]),
            )
            if quote is None:
                continue
            valid_bursts += 1
            references = reference_prices(
                quote,
                int(burst.price_raw),
                int(burst.direction),
            )
            for reference_name in config["reference_variants"]:
                for threshold in config["thresholds_ticks"]:
                    for horizon in config["horizons_ms"]:
                        labels.append(
                            _label_record(
                                burst,
                                reference_name,
                                references[reference_name],
                                int(threshold),
                                int(horizon),
                                int(config["ambiguity_window_ms"]),
                                trade_ticks,
                                trade_prices,
                                quote,
                            )
                        )

            primary_reference = references[config["primary_reference"]]
            primary_horizon = int(config["primary_horizon_ms"])
            for threshold in config["thresholds_ticks"]:
                threshold = int(threshold)
                for ambiguity in config[
                    "ambiguity_sensitivity_windows_ms"
                ]:
                    row = _label_record(
                        burst,
                        "MID",
                        primary_reference,
                        threshold,
                        primary_horizon,
                        int(ambiguity),
                        trade_ticks,
                        trade_prices,
                        quote,
                    )
                    sensitivity.append(
                        {
                            **row,
                            "sensitivity_type": "AMBIGUITY_WINDOW",
                            "base_threshold_ticks": threshold,
                            "parameter_value": int(ambiguity),
                        }
                    )
                perturbation = int(
                    config["threshold_perturbation_ticks"]
                )
                for varied_threshold in (
                    threshold - perturbation,
                    threshold,
                    threshold + perturbation,
                ):
                    row = _label_record(
                        burst,
                        "MID",
                        primary_reference,
                        int(varied_threshold),
                        primary_horizon,
                        int(config["ambiguity_window_ms"]),
                        trade_ticks,
                        trade_prices,
                        quote,
                    )
                    sensitivity.append(
                        {
                            **row,
                            "sensitivity_type": "THRESHOLD",
                            "base_threshold_ticks": threshold,
                            "parameter_value": int(varied_threshold),
                        }
                    )
                horizon_perturbation = int(
                    config["horizon_perturbation_ms"]
                )
                for varied_horizon in (
                    primary_horizon - horizon_perturbation,
                    primary_horizon,
                    primary_horizon + horizon_perturbation,
                ):
                    row = _label_record(
                        burst,
                        "MID",
                        primary_reference,
                        threshold,
                        int(varied_horizon),
                        int(config["ambiguity_window_ms"]),
                        trade_ticks,
                        trade_prices,
                        quote,
                    )
                    sensitivity.append(
                        {
                            **row,
                            "sensitivity_type": "HORIZON",
                            "base_threshold_ticks": threshold,
                            "parameter_value": int(varied_horizon),
                        }
                    )

        audits.append(
            {
                "session_date": str(session_value),
                "liquidity_bursts": len(burst_part),
                "valid_reference_bursts": valid_bursts,
                "reference_coverage": valid_bursts / max(len(burst_part), 1),
                "trade_source": str(trade_source),
                "depth_source": str(depth_source),
                **{f"trade_{key}": value for key, value in trade_qc.items()},
                **{f"depth_{key}": value for key, value in depth_qc.items()},
                **quote_audit,
                "status": "PASS",
            }
        )
        print(
            json.dumps(
                {
                    "processed": ordinal,
                    "sessions": bursts["session_date"].nunique(),
                    "session_date": str(session_value),
                    "bursts": len(burst_part),
                    "valid_references": valid_bursts,
                }
            ),
            flush=True,
        )
    return (
        pd.DataFrame(labels),
        pd.DataFrame(sensitivity),
        pd.DataFrame(audits),
    )


def distribution_table(labels: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    dimensions = {
        "ALL": pd.Series("ALL", index=labels.index),
        "SIDE": labels["lb_side"].astype(str),
        "SESSION": labels["session_date"].astype(str),
        "MONTH": labels["month"].astype(str),
        "YEAR": labels["year"].astype(str),
        "HOUR_NY": labels["hour_ny"].astype(str),
    }
    for (
        reference,
        threshold,
        horizon,
    ), part in labels.groupby(
        ["reference", "threshold_ticks", "horizon_ms"],
        sort=True,
    ):
        for dimension, values in dimensions.items():
            local_values = values.loc[part.index]
            for dimension_value, indices in local_values.groupby(
                local_values
            ).groups.items():
                subset = part.loc[indices]
                counts = subset["regime"].value_counts()
                for regime in REGIME_CLASSES:
                    count = int(counts.get(regime, 0))
                    records.append(
                        {
                            "reference": reference,
                            "threshold_ticks": threshold,
                            "horizon_ms": horizon,
                            "dimension": dimension,
                            "dimension_value": dimension_value,
                            "regime": regime,
                            "count": count,
                            "share": count / max(len(subset), 1),
                            "lb_count": len(subset),
                        }
                    )
    return pd.DataFrame(records)


def transition_table(labels: pd.DataFrame) -> pd.DataFrame:
    primary = labels[labels["reference"].eq("MID")]
    records: list[dict[str, object]] = []
    horizons = sorted(primary["horizon_ms"].unique())
    for threshold in sorted(primary["threshold_ticks"].unique()):
        part = primary[primary["threshold_ticks"].eq(threshold)]
        pivot = part.pivot(
            index="lb_id",
            columns="horizon_ms",
            values="regime",
        )
        for left, right in zip(horizons[:-1], horizons[1:]):
            counts = Counter(zip(pivot[left], pivot[right]))
            for (from_regime, to_regime), count in sorted(counts.items()):
                records.append(
                    {
                        "threshold_ticks": threshold,
                        "from_horizon_ms": left,
                        "to_horizon_ms": right,
                        "from_regime": from_regime,
                        "to_regime": to_regime,
                        "count": count,
                        "share": count / max(len(pivot), 1),
                    }
                )
    return pd.DataFrame(records)


def _agreement(
    left: pd.Series,
    right: pd.Series,
) -> float:
    paired = pd.concat([left, right], axis=1).dropna()
    return (
        float((paired.iloc[:, 0] == paired.iloc[:, 1]).mean())
        if len(paired)
        else math.nan
    )


def stability_and_gates(
    labels: pd.DataFrame,
    sensitivity: pd.DataFrame,
    audits: pd.DataFrame,
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    primary_horizon = int(config["primary_horizon_ms"])
    primary = labels[
        labels["horizon_ms"].eq(primary_horizon)
        & labels["ambiguity_window_ms"].eq(
            int(config["ambiguity_window_ms"])
        )
    ]
    reference_pivot = primary.pivot(
        index=["lb_id", "threshold_ticks"],
        columns="reference",
        values="regime",
    )
    reference_records: list[dict[str, object]] = []
    for threshold in config["thresholds_ticks"]:
        part = reference_pivot.xs(int(threshold), level="threshold_ticks")
        for right in ("EXECUTABLE", "LAST_TRADE"):
            reference_records.append(
                {
                    "threshold_ticks": int(threshold),
                    "left_reference": "MID",
                    "right_reference": right,
                    "n": int(part[["MID", right]].dropna().shape[0]),
                    "agreement": _agreement(part["MID"], part[right]),
                }
            )
    reference_table = pd.DataFrame(reference_records)

    stability_records: list[dict[str, object]] = []
    for threshold in config["thresholds_ticks"]:
        threshold = int(threshold)
        for sensitivity_type, center in (
            (
                "AMBIGUITY_WINDOW",
                int(config["ambiguity_window_ms"]),
            ),
            ("THRESHOLD", threshold),
            ("HORIZON", primary_horizon),
        ):
            part = sensitivity[
                sensitivity["base_threshold_ticks"].eq(threshold)
                & sensitivity["sensitivity_type"].eq(sensitivity_type)
            ]
            pivot = part.pivot(
                index="lb_id",
                columns="parameter_value",
                values="regime",
            )
            agreements = []
            for value in sorted(pivot.columns):
                if int(value) == center:
                    continue
                agreement = _agreement(pivot[center], pivot[value])
                agreements.append(agreement)
                stability_records.append(
                    {
                        "threshold_ticks": threshold,
                        "sensitivity_type": sensitivity_type,
                        "base_value": center,
                        "perturbed_value": int(value),
                        "n": len(pivot),
                        "agreement": agreement,
                    }
                )
            stability_records.append(
                {
                    "threshold_ticks": threshold,
                    "sensitivity_type": sensitivity_type,
                    "base_value": center,
                    "perturbed_value": "MIN",
                    "n": len(pivot),
                    "agreement": min(agreements),
                }
            )
    stability_table = pd.DataFrame(stability_records)

    total_bursts = int(audits["liquidity_bursts"].sum())
    valid_bursts = int(audits["valid_reference_bursts"].sum())
    coverage = valid_bursts / max(total_bursts, 1)
    gates = config["target_gates"]
    gate_records: list[dict[str, object]] = []
    for threshold in config["thresholds_ticks"]:
        threshold = int(threshold)
        part = primary[
            primary["reference"].eq("MID")
            & primary["threshold_ticks"].eq(threshold)
        ]
        counts = part["regime"].value_counts()
        shares = counts / max(len(part), 1)
        each_class_count = min(
            int(counts.get(regime, 0)) for regime in REGIME_CLASSES
        )
        maximum_share = max(
            float(shares.get(regime, 0.0)) for regime in REGIME_CLASSES
        )
        ambiguous_share = float(shares.get("AMBIGUOUS", 0.0))
        side_counts = pd.crosstab(part["lb_side"], part["regime"])
        side_probabilities = side_counts.div(
            side_counts.sum(axis=1),
            axis=0,
        ).reindex(columns=REGIME_CLASSES, fill_value=0.0)
        buy_sell_tvd = float(
            0.5
            * np.abs(
                side_probabilities.loc["BUY"]
                - side_probabilities.loc["SELL"]
            ).sum()
        )
        session_counts = pd.crosstab(
            part["session_date"],
            part["regime"],
        ).reindex(columns=REGIME_CLASSES, fill_value=0)
        minimum_sessions = min(
            int((session_counts[regime] > 0).sum())
            for regime in REGIME_CLASSES
        )
        maximum_concentration = max(
            float(
                session_counts[regime].max()
                / max(session_counts[regime].sum(), 1)
            )
            for regime in REGIME_CLASSES
        )
        reference_agreement = float(
            reference_table[
                reference_table["threshold_ticks"].eq(threshold)
                & reference_table["right_reference"].eq("EXECUTABLE")
            ]["agreement"].iloc[0]
        )
        sensitivity_minimums = {
            kind: float(
                stability_table[
                    stability_table["threshold_ticks"].eq(threshold)
                    & stability_table["sensitivity_type"].eq(kind)
                    & stability_table["perturbed_value"].eq("MIN")
                ]["agreement"].iloc[0]
            )
            for kind in (
                "AMBIGUITY_WINDOW",
                "THRESHOLD",
                "HORIZON",
            )
        }
        checks = {
            "coverage_pass": coverage
            >= float(gates["min_reference_coverage"]),
            "class_count_pass": each_class_count
            >= int(gates["min_count_each_class"]),
            "degeneracy_pass": maximum_share
            <= float(gates["max_single_class_share"]),
            "ambiguity_share_pass": ambiguous_share
            <= float(gates["max_ambiguous_share"]),
            "side_symmetry_pass": buy_sell_tvd
            <= float(gates["max_buy_sell_total_variation"]),
            "session_presence_pass": minimum_sessions
            >= int(gates["min_sessions_each_class"]),
            "session_concentration_pass": maximum_concentration
            <= float(gates["max_session_concentration_each_class"]),
            "reference_agreement_pass": reference_agreement
            >= float(gates["min_mid_executable_agreement"]),
            "ambiguity_stability_pass": sensitivity_minimums[
                "AMBIGUITY_WINDOW"
            ]
            >= float(gates["min_ambiguity_window_agreement"]),
            "threshold_stability_pass": sensitivity_minimums["THRESHOLD"]
            >= float(gates["min_threshold_perturbation_agreement"]),
            "horizon_stability_pass": sensitivity_minimums["HORIZON"]
            >= float(gates["min_horizon_perturbation_agreement"]),
        }
        gate_records.append(
            {
                "threshold_ticks": threshold,
                "reference_coverage": coverage,
                "minimum_class_count": each_class_count,
                "maximum_class_share": maximum_share,
                "ambiguous_share": ambiguous_share,
                "buy_sell_total_variation": buy_sell_tvd,
                "minimum_sessions_each_class": minimum_sessions,
                "maximum_session_concentration": maximum_concentration,
                "mid_executable_agreement": reference_agreement,
                "ambiguity_window_min_agreement": sensitivity_minimums[
                    "AMBIGUITY_WINDOW"
                ],
                "threshold_perturbation_min_agreement": sensitivity_minimums[
                    "THRESHOLD"
                ],
                "horizon_perturbation_min_agreement": sensitivity_minimums[
                    "HORIZON"
                ],
                **checks,
                "pass": all(checks.values()),
            }
        )
    gate_table = pd.DataFrame(gate_records)
    selected = None
    for threshold in config["threshold_selection_hierarchy"]:
        row = gate_table[gate_table["threshold_ticks"].eq(int(threshold))]
        if not row.empty and bool(row.iloc[0]["pass"]):
            selected = int(threshold)
            break
    return reference_table, stability_table, {
        "gate_table": gate_table,
        "selected_threshold_ticks": selected,
    }


def run(telegram_enabled: bool) -> dict[str, object]:
    frozen = verify_freeze()
    config = load_config(REGIME_CONFIG_PATH)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    telegram(
        "POST-LB REGIME | INICIO AUDITORIA OUTCOME-ONLY\n"
        "LB es la unidad. Matriz 4/8/12/16t x 0.5/1/2/5/10s. "
        "Sin training/AUC/PnL. Discovery SELLADO.",
        telegram_enabled,
    )
    labels, sensitivity, audits = build_labels(config)
    distributions = distribution_table(labels)
    transitions = transition_table(labels)
    reference_table, stability_table, gate_result = stability_and_gates(
        labels,
        sensitivity,
        audits,
        config,
    )
    gate_table = gate_result.pop("gate_table")
    selected = gate_result["selected_threshold_ticks"]
    result = {
        "audit_id": config["audit_id"],
        "status": (
            "TECHNICAL_REGIME_TARGET_CANDIDATE"
            if selected is not None
            else "REGIME_TARGET_INVALID"
        ),
        "liquidity_bursts": int(audits["liquidity_bursts"].sum()),
        "valid_reference_bursts": int(
            audits["valid_reference_bursts"].sum()
        ),
        "primary_reference": config["primary_reference"],
        "primary_horizon_ms": int(config["primary_horizon_ms"]),
        "ambiguity_window_ms": int(config["ambiguity_window_ms"]),
        **gate_result,
        "selection_did_not_use_model_metrics": True,
        "discovery_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "freeze_sha256": sha256_file(FREEZE_PATH),
        "input_freeze_status": frozen["status"],
    }
    labels.to_parquet(OUTPUT / "regime_labels.parquet", index=False)
    sensitivity.to_parquet(
        OUTPUT / "regime_sensitivity.parquet",
        index=False,
    )
    audits.to_csv(OUTPUT / "data_audit.csv", index=False)
    distributions.to_csv(
        OUTPUT / "regime_distribution.csv",
        index=False,
    )
    transitions.to_csv(
        OUTPUT / "regime_transition_matrix.csv",
        index=False,
    )
    reference_table.to_csv(
        OUTPUT / "reference_agreement.csv",
        index=False,
    )
    stability_table.to_csv(
        OUTPUT / "stability_audit.csv",
        index=False,
    )
    gate_table.to_csv(
        OUTPUT / "outcome_threshold_audit.csv",
        index=False,
    )
    distributions[
        distributions["dimension"].eq("ALL")
    ].to_csv(
        OUTPUT / "outcome_horizon_audit.csv",
        index=False,
    )
    write_json(OUTPUT / "result.json", result)
    artifact_names = (
        "regime_labels.parquet",
        "regime_sensitivity.parquet",
        "data_audit.csv",
        "regime_distribution.csv",
        "regime_transition_matrix.csv",
        "reference_agreement.csv",
        "stability_audit.csv",
        "outcome_threshold_audit.csv",
        "outcome_horizon_audit.csv",
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
            "POST-LB REGIME | RESULTADO AUDITORIA\n"
            f"Estado: {result['status']}\n"
            f"LB validos: {result['valid_reference_bursts']}/"
            f"{result['liquidity_bursts']}\n"
            f"Threshold candidato: {selected if selected is not None else 'NINGUNO'}t; "
            f"H={result['primary_horizon_ms']}ms\n"
            "Sin modelo/AUC/PnL. Discovery sigue SELLADO."
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
