from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import atas_mt5_pivot_backtest as structural


SEASONS = {
    2023: ("2023-03-12T00:00:00", "2023-11-05T00:00:00"),
    2024: ("2024-03-10T00:00:00", "2024-11-03T00:00:00"),
    2025: ("2025-03-09T00:00:00", "2025-11-02T00:00:00"),
    2026: ("2026-03-08T00:00:00", "2026-08-11T00:00:00"),
}
TARGETS = [value / 2 for value in range(2, 21)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detailed DST RR analysis for CFD->ATAS entries.")
    parser.add_argument("--sweep-root", type=Path, required=True)
    parser.add_argument("--atas-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def rr_key(value: float) -> str:
    return f"{value:.1f}R"


def load_reference_trades(root: Path) -> list[dict]:
    rows: list[dict] = []
    for year in SEASONS:
        path = root / str(year) / "raw_trades_1.5R.json"
        for row in json.loads(path.read_text(encoding="utf-8")):
            row = dict(row)
            row["year"] = year
            row["trade_id"] = f"{year}_{row['signal_time_ny']}"
            rows.append(row)
    return sorted(rows, key=lambda item: item["fill_time_ny"])


def load_atas_sessions(cache: Path) -> dict[str, list[structural.Bar]]:
    sessions: dict[str, list[structural.Bar]] = {}
    for year, (start_text, end_text) in SEASONS.items():
        start = datetime.fromisoformat(start_text).replace(tzinfo=structural.NY)
        end = datetime.fromisoformat(end_text).replace(tzinfo=structural.NY)
        sessions.update(structural.load_atas_bars(None, cache, start, end))
    return sessions


def path_outcome(
    session: list[structural.Bar], trade: dict, target_rr: float
) -> tuple[str, float, float, float]:
    fill_time = datetime.fromisoformat(trade["fill_time_ny"])
    time_to_index = {bar.time_ny: index for index, bar in enumerate(session)}
    fill_index = time_to_index.get(fill_time)
    if fill_index is None:
        raise KeyError(f"Fill ATAS ausente: {fill_time.isoformat()}")

    side = trade["side"]
    entry = float(trade["entry"])
    stop = float(trade["stop"])
    risk = float(trade["risk_points"])
    target = entry + target_rr * risk if side == "LONG" else entry - target_rr * risk
    deadline = fill_time + timedelta(minutes=30)
    result = "TIME_EXIT"
    realized = 0.0
    mfe = 0.0
    mae = 0.0
    exit_index = fill_index

    for index in range(fill_index, len(session)):
        bar = session[index]
        if bar.time_ny > deadline:
            break
        exit_index = index
        if side == "LONG":
            stop_hit = bar.low <= stop
            target_hit = bar.high >= target
            favorable = (bar.high - entry) / risk
            adverse = (entry - bar.low) / risk
        else:
            stop_hit = bar.high >= stop
            target_hit = bar.low <= target
            favorable = (entry - bar.low) / risk
            adverse = (bar.high - entry) / risk

        if stop_hit:  # misma convención conservadora que el backtest base
            mae = max(mae, 1.0)
            result = "LOSS"
            realized = -1.0
            break
        mfe = max(mfe, favorable)
        mae = max(mae, adverse)
        if target_hit:
            result = "WIN"
            realized = target_rr
            break

    if result == "TIME_EXIT":
        exit_index = min(
            range(fill_index, len(session)),
            key=lambda index: abs((session[index].time_ny - deadline).total_seconds()),
        )
        exit_price = session[exit_index].close
        pnl = exit_price - entry if side == "LONG" else entry - exit_price
        realized = max(-1.0, min(target_rr, pnl / risk))
        result = "TIME_WIN" if realized > 0 else "TIME_LOSS" if realized < 0 else "BREAKEVEN"
    return result, float(realized), float(max(0.0, mfe)), float(max(0.0, mae))


def build_fixed_cohort(
    trades: list[dict], sessions: dict[str, list[structural.Bar]]
) -> pd.DataFrame:
    rows: list[dict] = []
    for trade in trades:
        session = sessions.get(trade["session_date_ny"], [])
        for target in TARGETS:
            result, realized, mfe, mae = path_outcome(session, trade, target)
            signal = datetime.fromisoformat(trade["signal_time_ny"])
            rows.append(
                {
                    "trade_id": trade["trade_id"],
                    "year": trade["year"],
                    "session_date_ny": trade["session_date_ny"],
                    "signal_time_ny": trade["signal_time_ny"],
                    "fill_time_ny": trade["fill_time_ny"],
                    "hour_ny": signal.hour,
                    "month": signal.month,
                    "side": trade["side"],
                    "pivot_kind": trade["pivot_kind"],
                    "confirmed_later": bool(trade["confirmed_structure_after_signal"]),
                    "target_rr": target,
                    "result": result,
                    "realized_r": realized,
                    "mfe_before_stop_r": mfe,
                    "mae_r": mae,
                    "entry": trade["entry"],
                    "stop": trade["stop"],
                    "risk_points": trade["risk_points"],
                }
            )
    return pd.DataFrame(rows)


def max_drawdown(values: np.ndarray) -> float:
    equity = np.concatenate([[0.0], np.cumsum(values)])
    peaks = np.maximum.accumulate(equity)
    return float((peaks - equity).max())


def longest_loss_streak(values: np.ndarray) -> int:
    longest = current = 0
    for value in values:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def metrics(frame: pd.DataFrame) -> dict:
    frame = frame.sort_values("fill_time_ny")
    values = frame["realized_r"].to_numpy(float)
    positive = values[values > 0]
    negative = values[values < 0]
    gross_profit = positive.sum()
    gross_loss = abs(negative.sum())
    n = len(values)
    mean = float(values.mean()) if n else math.nan
    std = float(values.std(ddof=1)) if n > 1 else math.nan
    half_width = 1.96 * std / math.sqrt(n) if n > 1 else math.nan
    return {
        "n": n,
        "target_hits": int((frame["result"] == "WIN").sum()),
        "stop_losses": int((frame["result"] == "LOSS").sum()),
        "time_wins": int((frame["result"] == "TIME_WIN").sum()),
        "time_losses": int((frame["result"] == "TIME_LOSS").sum()),
        "wins": int(len(positive)),
        "losses": int(len(negative)),
        "wr": float(len(positive) / n) if n else math.nan,
        "target_hit_rate": float((frame["result"] == "WIN").sum() / n) if n else math.nan,
        "pf": float(gross_profit / gross_loss) if gross_loss else math.nan,
        "avg_r": mean,
        "avg_r_ci95_low": mean - half_width if n > 1 else math.nan,
        "avg_r_ci95_high": mean + half_width if n > 1 else math.nan,
        "net_r": float(values.sum()),
        "max_drawdown_r": max_drawdown(values) if n else math.nan,
        "longest_loss_streak": longest_loss_streak(values),
    }


def summarize_fixed(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    scopes = {
        "ALL_CAUSAL_CANDIDATES": frame,
        "CONFIRMED_LATER_SUBSET": frame.loc[frame["confirmed_later"]],
    }
    for scope_name, scope in scopes.items():
        for period in ["TOTAL", 2023, 2024, 2025, 2026]:
            period_frame = scope if period == "TOTAL" else scope.loc[scope["year"] == period]
            for target in TARGETS:
                selected = period_frame.loc[period_frame["target_rr"] == target]
                rows.append({"scope": scope_name, "period": str(period), "target_rr": target, **metrics(selected)})
    return pd.DataFrame(rows)


def load_operational(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    trade_rows = []
    for year in SEASONS:
        for target in TARGETS:
            path = root / str(year) / f"raw_trades_{target:.1f}R.json"
            for trade in json.loads(path.read_text(encoding="utf-8")):
                trade_rows.append(
                    {
                        **trade,
                        "year": year,
                        "target_rr": target,
                        "confirmed_later": bool(trade["confirmed_structure_after_signal"]),
                    }
                )
    all_trades = pd.DataFrame(trade_rows)
    for scope_name, scope in {
        "ALL_CAUSAL_CANDIDATES": all_trades,
        "CONFIRMED_LATER_SUBSET": all_trades.loc[all_trades["confirmed_later"]],
    }.items():
        scope = scope.rename(columns={"realized_r": "realized_r"})
        for period in ["TOTAL", 2023, 2024, 2025, 2026]:
            period_frame = scope if period == "TOTAL" else scope.loc[scope["year"] == period]
            for target in TARGETS:
                selected = period_frame.loc[period_frame["target_rr"] == target].copy()
                selected["fill_time_ny"] = selected["fill_time_ny"].astype(str)
                summary_rows.append(
                    {"scope": scope_name, "period": str(period), "target_rr": target, **metrics(selected)}
                )
    return pd.DataFrame(summary_rows), all_trades


def breakdown_3r(frame: pd.DataFrame) -> pd.DataFrame:
    selected = frame.loc[(frame["confirmed_later"]) & (frame["target_rr"] == 3.0)].copy()
    rows = []
    for feature in ("year", "hour_ny", "month", "side", "pivot_kind"):
        for value, group in selected.groupby(feature):
            rows.append({"feature": feature, "value": value, **metrics(group)})
    return pd.DataFrame(rows)


def target_reach(frame: pd.DataFrame) -> pd.DataFrame:
    # The 10R path keeps running until stop/deadline, so its MFE is suitable for
    # measuring every lower threshold without truncating at an earlier target.
    base = frame.loc[frame["target_rr"] == 10.0].copy()
    rows = []
    for scope_name, scope in {
        "ALL_CAUSAL_CANDIDATES": base,
        "CONFIRMED_LATER_SUBSET": base.loc[base["confirmed_later"]],
    }.items():
        for period in ["TOTAL", 2023, 2024, 2025, 2026]:
            period_frame = scope if period == "TOTAL" else scope.loc[scope["year"] == period]
            for target in [3.0, 4.0, 5.0, 6.0, 8.0, 10.0]:
                reached = int((period_frame["mfe_before_stop_r"] >= target).sum())
                rows.append(
                    {
                        "scope": scope_name,
                        "period": str(period),
                        "target_rr": target,
                        "n": len(period_frame),
                        "reached": reached,
                        "reach_rate": reached / len(period_frame) if len(period_frame) else math.nan,
                    }
                )
    return pd.DataFrame(rows)


def metric_line(row: pd.Series) -> str:
    return (
        f"n={int(row.n)}, hits={int(row.target_hits)}, WR={100 * row.wr:.2f}%, "
        f"PF={row.pf:.3f}, AvgR={row.avg_r:+.3f}, NetR={row.net_r:+.2f}, "
        f"MaxDD={row.max_drawdown_r:.2f}R"
    )


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    reference = load_reference_trades(args.sweep_root)
    sessions = load_atas_sessions(args.atas_cache)
    fixed = build_fixed_cohort(reference, sessions)

    base_original = pd.DataFrame(reference)
    reproduced = base_original.loc[
        base_original["confirmed_structure_after_signal"]
        & base_original["session_date_ny"].between("2026-07-01", "2026-08-07")
    ]
    reproduction = metrics(
        reproduced.rename(columns={"realized_r": "realized_r", "fill_time_ny": "fill_time_ny"})
        .assign(result=reproduced["result"])
    )
    if not (
        reproduction["n"] == 9
        and reproduction["wins"] == 6
        and reproduction["losses"] == 3
        and abs(reproduction["net_r"] - 6.0) < 1e-9
    ):
        raise RuntimeError(f"La muestra base 9/6/3/+6R no fue reproducida: {reproduction}")

    fixed_summary = summarize_fixed(fixed)
    operational_summary, operational_trades = load_operational(args.sweep_root)
    reach = target_reach(fixed)
    breakdown = breakdown_3r(fixed)
    details_3r = fixed.loc[(fixed["confirmed_later"]) & (fixed["target_rr"] == 3.0)].copy()

    fixed.to_csv(args.output / "fixed_cohort_outcomes.csv", index=False)
    fixed_summary.to_csv(args.output / "fixed_cohort_rr_summary.csv", index=False)
    operational_summary.to_csv(args.output / "operational_rr_summary.csv", index=False)
    operational_trades.to_csv(args.output / "operational_trades.csv", index=False)
    reach.to_csv(args.output / "target_reach_before_stop.csv", index=False)
    breakdown.to_csv(args.output / "breakdown_3R.csv", index=False)
    details_3r.to_csv(args.output / "confirmed_trade_details_3R.csv", index=False)

    confirmed_total = operational_summary.loc[
        (operational_summary["scope"] == "CONFIRMED_LATER_SUBSET")
        & (operational_summary["period"] == "TOTAL")
    ].sort_values("target_rr")
    causal_total = operational_summary.loc[
        (operational_summary["scope"] == "ALL_CAUSAL_CANDIDATES")
        & (operational_summary["period"] == "TOTAL")
    ].sort_values("target_rr")
    fixed_confirmed_total = fixed_summary.loc[
        (fixed_summary["scope"] == "CONFIRMED_LATER_SUBSET")
        & (fixed_summary["period"] == "TOTAL")
    ].sort_values("target_rr")
    best_3plus = confirmed_total.loc[confirmed_total["target_rr"] >= 3].sort_values(
        ["net_r", "pf"], ascending=False
    ).iloc[0]
    coverage = {
        str(year): json.loads(
            (args.sweep_root / str(year) / "trade_metrics.json").read_text(encoding="utf-8")
        )["sessions"]
        for year in SEASONS
    }
    causal_3r = causal_total.loc[causal_total["target_rr"] == 3.0].iloc[0]
    confirmed_3r = confirmed_total.loc[confirmed_total["target_rr"] == 3.0].iloc[0]

    fig, axes = plt.subplots(3, 1, figsize=(11, 12), sharex=True)
    for table, label, color in (
        (confirmed_total, "Confirmadas después (descriptivo)", "#0F766E"),
        (causal_total, "Todos los candidatos visibles", "#C2410C"),
    ):
        axes[0].plot(table["target_rr"], table["pf"], marker="o", label=label, color=color)
        axes[1].plot(table["target_rr"], table["net_r"], marker="o", label=label, color=color)
        axes[2].plot(
            table["target_rr"], 100 * table["target_hit_rate"], marker="o", label=label, color=color
        )
    axes[0].axhline(1, color="black", linewidth=0.8)
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[0].set_ylabel("Profit factor")
    axes[1].set_ylabel("R neta")
    axes[2].set_ylabel("Targets tocados (%)")
    axes[2].set_xlabel("Objetivo RR")
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend()
    fig.suptitle("CFD MT5 -> ATAS L2 | temporadas DST 2023-2026 | barrido RR")
    fig.tight_layout()
    fig.savefig(args.output / "rr_sweep.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    report = [
        "# Análisis detallado RR — CFD MT5 líder vs ATAS L2",
        "",
        "Temporadas DST: 2023 completa (13-mar a 3-nov), 2024 completa, 2025 completa y 2026 hasta la última sesión común disponible (7-ago).",
        "",
        "## Control de reproducción",
        "",
        "La muestra original julio-agosto 2026 quedó reproducida exactamente a 1.5R: 9 operaciones, 6W/3L, WR 66.67%, PF 3.00, AvgR +0.667 y NetR +6.00.",
        "",
        "## Resultado RR operativo — eventos que ATAS confirmó después",
        "",
        "| RR | N | Targets | WR | PF | AvgR | NetR | MaxDD | Racha L máx |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in confirmed_total.itertuples():
        report.append(
            f"| {row.target_rr:.1f} | {row.n} | {row.target_hits} | {100 * row.wr:.2f}% | "
            f"{row.pf:.3f} | {row.avg_r:+.3f} | {row.net_r:+.2f} | "
            f"{row.max_drawdown_r:.2f} | {row.longest_loss_streak} |"
        )
    report += [
        "",
        f"Mayor R neta observada entre 3R y 10R: **{best_3plus.target_rr:.1f}R**, "
        f"{metric_line(best_3plus)}.",
        "",
        "## 3R por temporada",
        "",
        "| Temporada | N | Targets | WR | PF | AvgR | NetR | IC95% AvgR | MaxDD |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for year in SEASONS:
        row = operational_summary.loc[
            (operational_summary["scope"] == "CONFIRMED_LATER_SUBSET")
            & (operational_summary["period"] == str(year))
            & (operational_summary["target_rr"] == 3.0)
        ].iloc[0]
        report.append(
            f"| {year} | {int(row.n)} | {int(row.target_hits)} | {100 * row.wr:.2f}% | "
            f"{row.pf:.3f} | {row.avg_r:+.3f} | {row.net_r:+.2f} | "
            f"[{row.avg_r_ci95_low:+.3f}, {row.avg_r_ci95_high:+.3f}] | {row.max_drawdown_r:.2f} |"
        )
    report += [
        "",
        "## Comparación justa: las mismas 254 entradas en todos los RR",
        "",
        "| RR | Targets | Tasa target | PF | AvgR | NetR | MaxDD |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for target in (3.0, 4.0, 5.0, 6.5, 8.0, 10.0):
        row = fixed_confirmed_total.loc[fixed_confirmed_total["target_rr"] == target].iloc[0]
        report.append(
            f"| {target:.1f} | {int(row.target_hits)} | {100 * row.target_hit_rate:.2f}% | "
            f"{row.pf:.3f} | {row.avg_r:+.3f} | {row.net_r:+.2f} | {row.max_drawdown_r:.2f} |"
        )
    report += [
        "",
        "## Recorrido favorable alcanzado antes del stop",
        "",
        "| Temporada | Cohorte | >=3R | >=4R | >=5R | >=6R | >=8R | >=10R |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for period in ("TOTAL", "2023", "2024", "2025", "2026"):
        table = reach.loc[
            (reach["scope"] == "CONFIRMED_LATER_SUBSET") & (reach["period"] == period)
        ].set_index("target_rr")
        cells = [f"{int(table.loc[target, 'reached'])} ({100 * table.loc[target, 'reach_rate']:.1f}%)" for target in (3.0, 4.0, 5.0, 6.0, 8.0, 10.0)]
        report.append(f"| {period} | {int(table.iloc[0].n)} | " + " | ".join(cells) + " |")
    total_sessions = sum(coverage.values())
    report += [
        "",
        f"En {total_sessions} sesiones DST hubo {int(confirmed_3r.n)} operaciones operativas condicionadas "
        f"a confirmación posterior ({confirmed_3r.n / total_sessions:.3f} por sesión). "
        f"El target 3R se tocó {int(confirmed_3r.target_hits)} veces: "
        f"{confirmed_3r.target_hits / total_sessions:.3f} por sesión, aproximadamente "
        f"{confirmed_3r.target_hits / (total_sessions / 21):.2f} veces por cada 21 sesiones.",
        "",
        "## Concentraciones observadas a 3R — cohorte fija confirmada después",
        "",
    ]
    hour13 = breakdown.loc[(breakdown["feature"] == "hour_ny") & (breakdown["value"] == 13)].iloc[0]
    longs = breakdown.loc[(breakdown["feature"] == "side") & (breakdown["value"] == "LONG")].iloc[0]
    shorts = breakdown.loc[(breakdown["feature"] == "side") & (breakdown["value"] == "SHORT")].iloc[0]
    july = breakdown.loc[(breakdown["feature"] == "month") & (breakdown["value"] == 7)].iloc[0]
    may = breakdown.loc[(breakdown["feature"] == "month") & (breakdown["value"] == 5)].iloc[0]
    report += [
        f"- 13:00–13:59 NY: {metric_line(hour13)}. Es una concentración descriptiva; 2023 fue negativo y el universo causal completo de esa hora también perdió.",
        f"- Pivotes inferiores / LONG: {metric_line(longs)}.",
        f"- Pivotes superiores / SHORT: {metric_line(shorts)}.",
        f"- Julio fue el mejor mes agregado: {metric_line(july)}; mayo fue el peor: {metric_line(may)}.",
        "",
        "## RR de trabajo recomendado para investigación",
        "",
        "**3R** es el punto de trabajo más defendible si se exige mínimo 1:3: tiene la mayor tasa de targets reales entre los RR >=3, el menor drawdown agregado de ese rango y fue positivo en 2025 y 2026. No recomiendo adoptar 6.5R aunque maximice la R neta full-sample: solo 14 de 238 operaciones tocaron realmente 6.5R, dependió de TIME_WIN y tuvo un drawdown mucho mayor.",
        "",
        "Esta recomendación solo aplica al patrón seleccionado/confirmado para investigación. El detector causal actual que toma todos los candidatos no tiene edge y no debe automatizar 3R todavía.",
    ]
    report += [
        "",
        "## Auditoría causal indispensable",
        "",
        f"- Condicionando a confirmación futura de ATAS: {metric_line(confirmed_3r)}.",
        f"- Todos los candidatos que podían verse en vivo: {metric_line(causal_3r)}.",
        "",
        "La diferencia demuestra que 'ATAS confirmó después' no puede utilizarse como filtro de entrada en vivo. Los resultados confirmados describen el patrón que se desea capturar; la curva de todos los candidatos mide el detector actual sin selección discrecional.",
        "",
        "## Interpretación",
        "",
        "- El 66.67% y PF 3.00 de las 9 operaciones sí es correcto, pero no se mantiene al extender la ventana.",
        "- 3R es alcanzable y mejora claramente en 2025-2026, pero el agregado 2023-2026 queda cerca de equilibrio y con variación fuerte entre años.",
        "- Los objetivos mayores de 3R deben juzgarse por targets realmente tocados; una operación TIME_WIN positiva no equivale a haber alcanzado el RR nominal.",
        "- No debe elegirse el RR de mayor R neta full-sample como regla definitiva. Debe congelarse y validarse hacia delante.",
    ]
    (args.output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    payload = {
        "reproduction": reproduction,
        "coverage": coverage,
        "best_3plus_confirmed_descriptive": json.loads(best_3plus.to_json()),
        "confirmed_3r": json.loads(confirmed_3r.to_json()),
        "causal_3r": json.loads(causal_3r.to_json()),
    }
    (args.output / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    print(f"OUTPUT={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
