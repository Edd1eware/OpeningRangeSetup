from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from atas_cache_decoder import load_cache_window  # noqa: E402
from telegram_run_summary_after_sync import send_persistent_text  # noqa: E402
from run_research import (  # noqa: E402
    CONFIG_PATH,
    load_session,
)
from src.efficiency_audit import (  # noqa: E402
    causal_depth_timestamps,
    compute_session_efficiencies,
    reconstruct_quotes,
    sniper_core_mask,
)
from src.vt_core import (  # noqa: E402
    NY,
    causalize_trade_timestamps,
    contiguous_trade_ticks,
    datetime_to_dotnet_ticks,
    load_config,
)


AUDIT_CONFIG_PATH = ROOT / "config" / "efficiency_audit_config.json"
AUDIT_PREREG_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "EFFICIENCY_AUDIT_PREREGISTRATION.md"
)
AUDIT_SOURCE_PATH = ROOT / "src" / "efficiency_audit.py"
AUDIT_TEST_PATH = ROOT / "tests" / "test_efficiency_audit.py"
FREEZE_PATH = (
    ROOT
    / "config"
    / "preregistration"
    / "EFFICIENCY_AUDIT_FREEZE_MANIFEST.json"
)
OUTPUT = ROOT / "artifacts" / "efficiency_audit"

VARIANT_PATHS = {
    "trade_path_efficiency_v1": "trade_path_length",
    "mid_efficiency_quote_changes": "mid_quote_path_length",
    "mid_efficiency_sampled_25ms": "mid_sampled_25ms_path_length",
    "mid_efficiency_sampled_50ms": "mid_sampled_50ms_path_length",
    "mid_efficiency_sampled_100ms": "mid_sampled_100ms_path_length",
    "microprice_efficiency": "microprice_path_length",
    "excursion_efficiency": "trade_path_length",
    "impulse_retention": "trade_path_length",
}
QUOTE_VARIANTS = {
    "mid_efficiency_quote_changes",
    "mid_efficiency_sampled_25ms",
    "mid_efficiency_sampled_50ms",
    "mid_efficiency_sampled_100ms",
    "microprice_efficiency",
}


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
    main_config = load_config(CONFIG_PATH)
    return send_persistent_text(
        main_config["telegram_results_folder"],
        message,
    )


def freeze() -> dict[str, object]:
    required = [
        AUDIT_CONFIG_PATH,
        AUDIT_PREREG_PATH,
        AUDIT_SOURCE_PATH,
        Path(__file__).resolve(),
        AUDIT_TEST_PATH,
        ROOT / "config" / "preregistration" / "FREEZE_MANIFEST.json",
        ROOT / "artifacts" / "smoke" / "manifest.json",
        ROOT / "artifacts" / "smoke" / "vt_candidates.parquet",
    ]
    manifest = {
        "audit_id": load_config(AUDIT_CONFIG_PATH)["audit_id"],
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BEFORE_EFFICIENCY_VARIANT_OUTPUTS",
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in required
        },
        "discovery_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
    }
    write_json(FREEZE_PATH, manifest)
    return manifest


def verify_freeze() -> dict[str, object]:
    if not FREEZE_PATH.is_file():
        raise RuntimeError("efficiency audit is not frozen")
    manifest = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        path = ROOT / relative
        observed = sha256_file(path)
        if observed != expected["sha256"]:
            raise RuntimeError(
                f"frozen file changed: {relative}: "
                f"{observed}!={expected['sha256']}"
            )
    return manifest


def depth_bounds(session_date: date, config: dict) -> tuple[int, int]:
    warmup = time.fromisoformat(config["depth_warmup_start_ny"])
    end = time.fromisoformat(config["depth_end_ny"])
    return (
        datetime_to_dotnet_ticks(
            datetime.combine(session_date, warmup, tzinfo=NY)
        ),
        datetime_to_dotnet_ticks(
            datetime.combine(session_date, end, tzinfo=NY)
        ),
    )


def build_dataset(config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    main_config = load_config(CONFIG_PATH)
    source_candidates = pd.read_parquet(
        ROOT / "artifacts" / "smoke" / "vt_candidates.parquet"
    )
    source_candidates = source_candidates.copy()
    source_candidates["sniper_core"] = sniper_core_mask(
        source_candidates,
        config["sniper_core_gates"],
    ).astype(np.int8)
    cache_root = Path(main_config["cache_root"])
    session_outputs: list[pd.DataFrame] = []
    audits: list[dict[str, object]] = []

    for ordinal, (session_value, candidate_part) in enumerate(
        source_candidates.groupby("session_date", sort=True),
        start=1,
    ):
        session_date = date.fromisoformat(str(session_value))
        context, raw_trades, trade_source = load_session(
            session_date,
            cache_root,
        )
        trades, trade_qc = causalize_trade_timestamps(
            raw_trades,
            main_config["timestamp_qc"],
        )
        trade_ticks = contiguous_trade_ticks(trades)

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
            not math.isclose(context.tick_size, depth_context.tick_size)
            or not math.isclose(context.lot_size, depth_context.lot_size)
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
        result = compute_session_efficiencies(
            candidate_part,
            trades,
            trade_ticks,
            quotes,
            depth_ticks,
            config,
        )
        comparison = result.merge(
            candidate_part[
                [
                    "lb_id",
                    "candidate_ticks",
                    "candidate_side",
                    "directional_efficiency_2000ms",
                ]
            ],
            on=["lb_id", "candidate_ticks", "candidate_side"],
            how="left",
            validate="one_to_one",
        )
        difference = np.abs(
            comparison["trade_path_efficiency_v1"]
            - comparison["directional_efficiency_2000ms"]
        )
        maximum_difference = float(difference.max())
        if maximum_difference != 0.0:
            raise AssertionError(
                f"trade V1 mismatch {session_value}: {maximum_difference}"
            )
        session_outputs.append(result)
        audit = {
            "session_date": str(session_value),
            "trade_source": str(trade_source),
            "depth_source": str(depth_source),
            "candidate_rows": len(result),
            "trade_v1_max_abs_difference": maximum_difference,
            **{f"trade_{key}": value for key, value in trade_qc.items()},
            **{f"depth_{key}": value for key, value in depth_qc.items()},
            **quote_audit,
            "status": "PASS",
        }
        audits.append(audit)
        print(
            json.dumps(
                {
                    "processed": ordinal,
                    "sessions": source_candidates[
                        "session_date"
                    ].nunique(),
                    "session_date": str(session_value),
                    "candidates": len(result),
                    "quote_events": len(quotes.ticks),
                }
            ),
            flush=True,
        )
    return pd.concat(session_outputs, ignore_index=True), pd.DataFrame(audits)


def distributions(
    data: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    groups = {
        "ALL": pd.Series(True, index=data.index),
        "SNIPER_CORE": data["sniper_core"].eq(1),
        "BUY": data["candidate_side"].eq("BUY"),
        "SELL": data["candidate_side"].eq("SELL"),
    }
    quantiles = [
        float(value) for value in config["distribution_quantiles"]
    ]
    records: list[dict[str, object]] = []
    for variant in VARIANT_PATHS:
        for group_name, mask in groups.items():
            values = pd.to_numeric(
                data.loc[mask, variant],
                errors="coerce",
            )
            finite = values[np.isfinite(values)]
            record: dict[str, object] = {
                "variant": variant,
                "group": group_name,
                "rows": len(values),
                "valid": len(finite),
                "missing": int(values.isna().sum()),
                "coverage": len(finite) / max(len(values), 1),
                "mean": float(finite.mean()) if len(finite) else math.nan,
                "std": float(finite.std()) if len(finite) else math.nan,
            }
            for quantile, value in finite.quantile(quantiles).items():
                token = f"q{int(round(float(quantile) * 100)):02d}"
                record[token] = float(value)
            records.append(record)
    return pd.DataFrame(records)


def correlations(data: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for variant, path_column in VARIANT_PATHS.items():
        variables = {
            "TradeCount": "trade_count",
            "TradeRate": "trade_rate",
            "DOMUpdateCount": "dom_update_count",
            "PathLength": path_column,
        }
        for label, column in variables.items():
            paired = data[[variant, column]].replace(
                [np.inf, -np.inf],
                np.nan,
            ).dropna()
            records.append(
                {
                    "variant": variant,
                    "activity": label,
                    "path_column": path_column,
                    "n": len(paired),
                    "pearson": (
                        float(paired[variant].corr(paired[column], method="pearson"))
                        if len(paired) >= 3
                        else math.nan
                    ),
                    "spearman": (
                        float(paired[variant].corr(paired[column], method="spearman"))
                        if len(paired) >= 3
                        else math.nan
                    ),
                }
            )
    return pd.DataFrame(records)


def session_distributions(data: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for variant in VARIANT_PATHS:
        for (session_date, side), part in data.groupby(
            ["session_date", "candidate_side"],
            sort=True,
        ):
            values = pd.to_numeric(part[variant], errors="coerce")
            finite = values[np.isfinite(values)]
            records.append(
                {
                    "variant": variant,
                    "session_date": session_date,
                    "side": side,
                    "rows": len(part),
                    "valid": len(finite),
                    "coverage": len(finite) / max(len(part), 1),
                    "median": (
                        float(finite.median()) if len(finite) else math.nan
                    ),
                    "mean": (
                        float(finite.mean()) if len(finite) else math.nan
                    ),
                }
            )
    return pd.DataFrame(records)


def mechanical_gates(
    data: pd.DataFrame,
    correlation_table: pd.DataFrame,
    session_table: pd.DataFrame,
    config: dict,
) -> tuple[pd.DataFrame, dict[str, object]]:
    gates = config["mechanical_gates"]
    baseline_rows = correlation_table[
        correlation_table["variant"].eq("trade_path_efficiency_v1")
        & correlation_table["activity"].isin(
            ["TradeCount", "DOMUpdateCount", "PathLength"]
        )
    ]
    baseline_nuisance = float(
        baseline_rows["spearman"].abs().max()
    )

    sampled = [
        "mid_efficiency_sampled_25ms",
        "mid_efficiency_sampled_50ms",
        "mid_efficiency_sampled_100ms",
    ]
    pairwise: list[dict[str, object]] = []
    mid_robust = True
    for left_index, left in enumerate(sampled):
        for right in sampled[left_index + 1 :]:
            paired = data[[left, right]].dropna()
            rho = float(paired[left].corr(paired[right], method="spearman"))
            median_difference = float(
                np.median(np.abs(paired[left] - paired[right]))
            )
            passed = (
                rho
                >= float(gates["min_mid_sampling_pairwise_spearman"])
                and median_difference
                <= float(
                    gates["max_mid_sampling_median_abs_difference"]
                )
            )
            mid_robust = mid_robust and passed
            pairwise.append(
                {
                    "left": left,
                    "right": right,
                    "n": len(paired),
                    "spearman": rho,
                    "median_abs_difference": median_difference,
                    "pass": passed,
                }
            )

    records: list[dict[str, object]] = []
    for variant in VARIANT_PATHS:
        values = pd.to_numeric(data[variant], errors="coerce")
        finite = values[np.isfinite(values)]
        coverage = len(finite) / max(len(values), 1)
        minimum_coverage = float(
            gates[
                "min_quote_variant_coverage"
                if variant in QUOTE_VARIANTS
                else "min_trade_variant_coverage"
            ]
        )
        bounded = bool(
            len(finite)
            and finite.ge(-1e-12).all()
            and finite.le(1.0 + 1e-12).all()
        )
        buy = data.loc[data["candidate_side"].eq("BUY"), variant].dropna()
        sell = data.loc[data["candidate_side"].eq("SELL"), variant].dropna()
        median_difference = abs(float(buy.median()) - float(sell.median()))
        ks_statistic = float(ks_2samp(buy, sell).statistic)
        side_pass = (
            median_difference
            <= float(gates["max_abs_buy_sell_median_difference"])
            and ks_statistic
            <= float(gates["max_buy_sell_ks_statistic"])
        )
        variant_sessions = session_table[
            session_table["variant"].eq(variant)
        ]
        minimum_session_coverage = float(
            variant_sessions["coverage"].min()
        )
        session_pass = (
            minimum_session_coverage
            >= float(gates["min_quote_session_coverage"])
            if variant in QUOTE_VARIANTS
            else True
        )
        nuisance_rows = correlation_table[
            correlation_table["variant"].eq(variant)
            & correlation_table["activity"].isin(
                ["TradeCount", "DOMUpdateCount", "PathLength"]
            )
        ]
        nuisance_max = float(nuisance_rows["spearman"].abs().max())
        nuisance_improvement = baseline_nuisance - nuisance_max
        nuisance_pass = (
            nuisance_improvement
            >= float(gates["min_nuisance_improvement_vs_trade_v1"])
        )
        sampling_pass = (
            mid_robust
            if variant == "mid_efficiency_sampled_50ms"
            else True
        )
        pass_status = bool(
            coverage >= minimum_coverage
            and bounded
            and side_pass
            and session_pass
            and nuisance_pass
            and sampling_pass
        )
        records.append(
            {
                "variant": variant,
                "coverage": coverage,
                "coverage_pass": coverage >= minimum_coverage,
                "bounded_pass": bounded,
                "buy_sell_median_abs_difference": median_difference,
                "buy_sell_ks_statistic": ks_statistic,
                "side_symmetry_pass": side_pass,
                "minimum_session_coverage": minimum_session_coverage,
                "session_coverage_pass": session_pass,
                "baseline_nuisance_max_abs_spearman": baseline_nuisance,
                "variant_nuisance_max_abs_spearman": nuisance_max,
                "nuisance_improvement": nuisance_improvement,
                "nuisance_pass": nuisance_pass,
                "mid_sampling_robustness_pass": sampling_pass,
                "pass": pass_status,
            }
        )
    table = pd.DataFrame(records)
    selected = None
    for variant in config["selection_hierarchy"]:
        row = table[table["variant"].eq(variant)]
        if not row.empty and bool(row.iloc[0]["pass"]):
            selected = variant
            break
    return table, {
        "baseline_nuisance_max_abs_spearman": baseline_nuisance,
        "mid_sampling_pairwise": pairwise,
        "mid_sampling_robustness_pass": mid_robust,
        "selected_measure": selected,
    }


def run(telegram_enabled: bool) -> dict[str, object]:
    frozen = verify_freeze()
    config = load_config(AUDIT_CONFIG_PATH)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    telegram(
        "VT TIER1 | INICIO AUDITORIA EFFICIENCY OUTCOME-ONLY\n"
        "Discovery sellado. SNIPER_CORE solo diagnostico. "
        "Sin training/AUC/PnL; seleccion prohibe tasa de positivos.",
        telegram_enabled,
    )
    data, audit = build_dataset(config)
    distribution_table = distributions(data, config)
    correlation_table = correlations(data)
    session_table = session_distributions(data)
    gate_table, selection = mechanical_gates(
        data,
        correlation_table,
        session_table,
        config,
    )
    selected = selection["selected_measure"]
    result = {
        "audit_id": config["audit_id"],
        "status": (
            "MECHANICALLY_VALID_MEASURE_FOUND"
            if selected
            else "NO_MECHANICALLY_VALID_EFFICIENCY_V2"
        ),
        "candidate_rows": len(data),
        "sessions": int(data["session_date"].nunique()),
        "sniper_core_rows": int(data["sniper_core"].sum()),
        "trade_v1_status": "DEGENERATE_TARGET_COMPONENT",
        "trade_v1_threshold": 0.65,
        "selected_measure": selected,
        "selection_did_not_use_positive_rate": True,
        "discovery_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        **selection,
        "freeze_sha256": sha256_file(FREEZE_PATH),
        "input_freeze_status": frozen["status"],
    }
    data.to_parquet(OUTPUT / "efficiency_candidates.parquet", index=False)
    audit.to_csv(OUTPUT / "data_audit.csv", index=False)
    distribution_table.to_csv(
        OUTPUT / "distributions.csv",
        index=False,
    )
    correlation_table.to_csv(
        OUTPUT / "correlations.csv",
        index=False,
    )
    session_table.to_csv(
        OUTPUT / "session_distributions.csv",
        index=False,
    )
    gate_table.to_csv(OUTPUT / "mechanical_gates.csv", index=False)
    write_json(OUTPUT / "result.json", result)
    artifact_names = (
        "efficiency_candidates.parquet",
        "data_audit.csv",
        "distributions.csv",
        "correlations.csv",
        "session_distributions.csv",
        "mechanical_gates.csv",
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
            "VT TIER1 | RESULTADO AUDITORIA EFFICIENCY\n"
            f"Estado: {result['status']}\n"
            f"Candidatos: {result['candidate_rows']}; "
            f"SNIPER_CORE: {result['sniper_core_rows']}\n"
            f"Medida: {selected or 'NINGUNA'}\n"
            "Seleccion sin positivos/AUC/PnL. Discovery sigue SELLADO."
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
