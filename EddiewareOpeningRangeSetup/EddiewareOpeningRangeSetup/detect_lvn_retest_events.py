#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from lvn_retest_engine.config import ResearchConfig, parse_clock
from lvn_retest_engine.main import result_json, run_research


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detector causal de LVN 09:30-09:31 ET y retests 09:31-09:40 ET.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", nargs="+", required=True, help="Archivos o globs CSV/Parquet con ticks o footprint largo")
    parser.add_argument("--output", required=True, help="Workbook .xlsx de salida")
    parser.add_argument("--dates", nargs="*", help="Lista exacta de sesiones YYYY-MM-DD")
    parser.add_argument("--from-date", help="Fecha mínima inclusiva")
    parser.add_argument("--to-date", help="Fecha máxima inclusiva")
    parser.add_argument("--symbol", default="NQ")
    parser.add_argument("--tick-size", type=float, default=0.25)
    parser.add_argument("--input-timezone", default="America/New_York", help="Zona de timestamps sin offset; epoch siempre se interpreta UTC")
    parser.add_argument("--context-profile-start", type=parse_clock, default=parse_clock("08:30:00"))
    parser.add_argument("--context-profile-end", type=parse_clock, default=parse_clock("09:30:00"))
    parser.add_argument("--lvn-profile-start", type=parse_clock, default=parse_clock("09:30:00"))
    parser.add_argument("--lvn-profile-end", type=parse_clock, default=parse_clock("09:31:00"))
    parser.add_argument("--retest-start", type=parse_clock, default=parse_clock("09:31:00"))
    parser.add_argument("--retest-end", type=parse_clock, default=parse_clock("09:40:00"))
    parser.add_argument("--lvn-neighbor-levels", type=int, default=2)
    parser.add_argument("--lvn-max-percent-of-neighbors", type=float, default=0.50)
    parser.add_argument("--min-total-volume-at-profile", type=float, default=1.0)
    parser.add_argument("--min-lvn-volume", type=float, default=1.0)
    parser.add_argument("--max-lvn-volume-percent-of-poc", type=float, default=0.50)
    parser.add_argument("--hvn-neighbor-levels", type=int, default=2)
    parser.add_argument("--hvn-min-percent-of-neighbors", type=float, default=1.25)
    parser.add_argument("--retest-tolerance-ticks", type=int, default=0)
    parser.add_argument("--retest-rearm-ticks", type=int, default=1)
    parser.add_argument("--resolution-confirm-ticks", type=int, default=1, help="Ticks más allá del borde de la zona LVN para confirmar aceptación (atraviesa) o rechazo (regresa)")
    parser.add_argument("--imbalance-ratio", type=float, default=3.0)
    parser.add_argument("--imbalance-min-compare-volume", type=float, default=5.0)
    parser.add_argument("--big-trade-min-size", type=float, default=20.0)
    parser.add_argument("--value-area-pct", type=float, default=0.70)
    parser.add_argument("--shape-temperature", type=float, default=0.22)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = ResearchConfig(
        symbol=args.symbol,
        tick_size=args.tick_size,
        input_timezone=args.input_timezone,
        context_profile_start=args.context_profile_start,
        context_profile_end=args.context_profile_end,
        lvn_profile_start=args.lvn_profile_start,
        lvn_profile_end=args.lvn_profile_end,
        retest_start=args.retest_start,
        retest_end=args.retest_end,
        lvn_neighbor_levels=args.lvn_neighbor_levels,
        lvn_max_percent_of_neighbors=args.lvn_max_percent_of_neighbors,
        min_total_volume_at_profile=args.min_total_volume_at_profile,
        min_lvn_volume=args.min_lvn_volume,
        max_lvn_volume_percent_of_poc=args.max_lvn_volume_percent_of_poc,
        hvn_neighbor_levels=args.hvn_neighbor_levels,
        hvn_min_percent_of_neighbors=args.hvn_min_percent_of_neighbors,
        retest_tolerance_ticks=args.retest_tolerance_ticks,
        retest_rearm_ticks=args.retest_rearm_ticks,
        resolution_confirm_ticks=args.resolution_confirm_ticks,
        imbalance_ratio=args.imbalance_ratio,
        imbalance_min_compare_volume=args.imbalance_min_compare_volume,
        big_trade_min_size=args.big_trade_min_size,
        value_area_pct=args.value_area_pct,
        shape_temperature=args.shape_temperature,
    )
    try:
        result = run_research(
            args.input,
            args.output,
            config,
            session_dates=set(args.dates) if args.dates else None,
            from_date=args.from_date,
            to_date=args.to_date,
        )
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(result_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
