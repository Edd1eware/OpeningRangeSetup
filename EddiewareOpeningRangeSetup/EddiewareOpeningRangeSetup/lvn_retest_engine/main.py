from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from .config import ResearchConfig
from .exporter import build_summary, export_results
from .feature_extractor import build_daily_market_context, session_features
from .hvn_detector import detect_hvns
from .io import read_inputs
from .lvn_detector import detect_lvns
from .profile_builder import build_profile, flatten_profile
from .retest_detector import detect_retests
from .shape_classifier import classify_shape


def _decorate_debug(rows: list[dict[str, object]], session_date: object, profile_name: str) -> list[dict[str, object]]:
    decorated: list[dict[str, object]] = []
    for row in rows:
        decorated.append({"date": str(session_date), "profile": profile_name, **row})
    return decorated


def run_research(
    input_patterns: list[str],
    output_path: str | Path,
    config: ResearchConfig,
    session_dates: set[str] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, object]:
    data, manifest, input_debug = read_inputs(input_patterns, config)
    date_strings = data["session_date"].map(lambda value: value.isoformat())
    if session_dates is not None:
        data = data.loc[date_strings.isin(session_dates)].copy()
    else:
        if from_date:
            data = data.loc[date_strings >= from_date].copy()
            date_strings = data["session_date"].map(lambda value: value.isoformat())
        if to_date:
            data = data.loc[date_strings <= to_date].copy()
    if data.empty:
        raise ValueError("No quedaron filas dentro del filtro de fechas solicitado")
    daily_market = build_daily_market_context(data, config)
    daily_market_map = {
        row["session_date"]: row for row in daily_market.to_dict(orient="records")
    } if not daily_market.empty else {}

    daily_rows: list[dict[str, object]] = []
    lvn_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    no_retest_rows: list[dict[str, object]] = []
    debug_rows: list[dict[str, object]] = list(input_debug)
    debug_rows.extend({"debug_type": "INPUT_MANIFEST", "status": "ACCEPTED", **row} for row in manifest)

    for session_date, session_frame in data.groupby("session_date", sort=True):
        context = build_profile(
            session_frame,
            session_date,
            "CONTEXT_0830_0930",
            config.context_profile_start,
            config.context_profile_end,
            config,
        )
        minute = build_profile(
            session_frame,
            session_date,
            "FIRST_MINUTE_0930_0931",
            config.lvn_profile_start,
            config.lvn_profile_end,
            config,
        )
        for profile in (context, minute):
            profile.hvns, hvn_debug = detect_hvns(profile, config)
            profile.lvns, lvn_debug = detect_lvns(profile, config)
            profile.shape = classify_shape(profile, config)
            debug_rows.extend(_decorate_debug(hvn_debug, session_date, profile.profile_name))
            debug_rows.extend(_decorate_debug(lvn_debug, session_date, profile.profile_name))

        day_context = daily_market_map.get(session_date)
        features = session_features(session_frame, context, minute, day_context, config)
        events, retest_debug = detect_retests(
            session_frame,
            session_date,
            minute,
            context,
            features,
            config,
        )
        debug_rows.extend(_decorate_debug(retest_debug, session_date, "FIRST_MINUTE_0930_0931"))
        event_rows.extend(events)

        day_row: dict[str, object] = {
            "date": session_date.isoformat(),
            "symbol": str(session_frame["symbol"].iloc[0]),
            **features,
            **flatten_profile(context, "context_"),
            **flatten_profile(minute, "minute_"),
            "first_minute_lvn_count": len(minute.lvns),
            "retest_event_count": len(events),
            "has_any_retest": bool(events),
        }
        daily_rows.append(day_row)

        event_counts: dict[str, int] = {}
        for event in events:
            event_counts[str(event["lvn_id"])] = event_counts.get(str(event["lvn_id"]), 0) + 1
        for node in minute.lvns:
            lvn_rows.append({
                "date": session_date.isoformat(),
                "symbol": str(session_frame["symbol"].iloc[0]),
                **node,
                "retest_count": event_counts.get(str(node["lvn_id"]), 0),
                "had_retest": event_counts.get(str(node["lvn_id"]), 0) > 0,
                "context_profile_shape": context.shape.get("profile_shape"),
                "context_shape_confidence": context.shape.get("shape_confidence_score"),
                "minute_profile_shape": minute.shape.get("profile_shape"),
                "minute_shape_confidence": minute.shape.get("shape_confidence_score"),
                **{f"context_{key}": value for key, value in context.shape.items() if key.startswith("prob_")},
                **{f"minute_{key}": value for key, value in minute.shape.items() if key.startswith("prob_")},
            })
        if minute.lvns and not events:
            no_retest_rows.append({
                "date": session_date.isoformat(),
                "symbol": str(session_frame["symbol"].iloc[0]),
                "lvn_count": len(minute.lvns),
                "lvn_ids": "|".join(str(node["lvn_id"]) for node in minute.lvns),
                "lvn_prices": "|".join(f"{float(node['price']):.2f}" for node in minute.lvns),
                "context_profile_shape": context.shape.get("profile_shape"),
                "context_prob_P": context.shape.get("prob_P"),
                "context_prob_b": context.shape.get("prob_b"),
                "context_prob_D": context.shape.get("prob_D"),
                "reason": "LVN_DETECTED_BUT_NOT_RETESTED_BEFORE_0940",
            })

    daily_df = pd.DataFrame(daily_rows)
    lvn_df = pd.DataFrame(lvn_rows)
    events_df = pd.DataFrame(event_rows)
    no_retest_df = pd.DataFrame(no_retest_rows)
    debug_df = pd.DataFrame(debug_rows)
    summary_df = build_summary(events_df, daily_df, lvn_df)
    sheets = {
        "Summary": summary_df,
        "Daily_Profile": daily_df,
        "LVN_Profile": lvn_df,
        "LVN_Events": events_df,
        "No_Retest": no_retest_df,
        "Debug": debug_df,
    }
    excel_path, csv_dir = export_results(output_path, sheets)
    return {
        "excel_path": str(excel_path),
        "csv_dir": str(csv_dir),
        "sessions": len(daily_df),
        "lvns": len(lvn_df),
        "events": len(events_df),
        "no_retest_days": len(no_retest_df),
        "input_files": len(manifest),
    }


def result_json(result: dict[str, object]) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False)
