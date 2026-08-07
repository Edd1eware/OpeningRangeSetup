from __future__ import annotations

import hashlib
import heapq
import json
import math
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from atas_cache_decoder import load_cache_window  # noqa: E402
from run_research import CONFIG_PATH  # noqa: E402
from src.efficiency_audit import causal_depth_timestamps  # noqa: E402
from src.vt_core import (  # noqa: E402
    NY,
    TICKS_PER_MILLISECOND,
    datetime_to_dotnet_ticks,
    load_config,
)


OUTPUT = ROOT / "artifacts" / "quote_state_smoke_audit"
DETAIL_PATH = OUTPUT / "quote_state_by_lb.csv"
SUMMARY_PATH = OUTPUT / "summary.json"
REPORT_PATH = OUTPUT / "REPORT.md"
MANIFEST_PATH = OUTPUT / "manifest.json"
BURSTS_PATH = ROOT / "artifacts" / "smoke" / "liquidity_bursts.csv"
LABELS_PATH = (
    ROOT
    / "artifacts"
    / "post_lb_regime_audit"
    / "regime_labels.parquet"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def depth_bounds(session_date: date) -> tuple[int, int]:
    return (
        datetime_to_dotnet_ticks(
            datetime.combine(session_date, time(9, 25), tzinfo=NY)
        ),
        datetime_to_dotnet_ticks(
            datetime.combine(
                session_date,
                time(16, 0, 20),
                tzinfo=NY,
            )
        ),
    )


def valid_book_state(
    bid_volume: dict[int, int],
    ask_volume: dict[int, int],
    bid_heap: list[int],
    ask_heap: list[int],
) -> tuple[int, int, int, int] | None:
    while bid_heap and -bid_heap[0] not in bid_volume:
        heapq.heappop(bid_heap)
    while ask_heap and ask_heap[0] not in ask_volume:
        heapq.heappop(ask_heap)
    if not bid_heap or not ask_heap:
        return None
    best_bid = -bid_heap[0]
    best_ask = ask_heap[0]
    spread = best_ask - best_bid
    if spread < 1 or spread > 4:
        return None
    return (
        best_bid,
        best_ask,
        bid_volume[best_bid],
        ask_volume[best_ask],
    )


def state_fields(
    state: tuple[int, int, int, int] | None,
    prefix: str,
) -> dict[str, float | int | None]:
    if state is None:
        return {
            f"{prefix}_best_bid_raw": None,
            f"{prefix}_best_ask_raw": None,
            f"{prefix}_bid_size": None,
            f"{prefix}_ask_size": None,
            f"{prefix}_mid_raw": None,
            f"{prefix}_microprice_raw": None,
        }
    best_bid, best_ask, bid_size, ask_size = state
    return {
        f"{prefix}_best_bid_raw": best_bid,
        f"{prefix}_best_ask_raw": best_ask,
        f"{prefix}_bid_size": bid_size,
        f"{prefix}_ask_size": ask_size,
        f"{prefix}_mid_raw": (best_bid + best_ask) / 2.0,
        f"{prefix}_microprice_raw": (
            best_ask * bid_size + best_bid * ask_size
        )
        / (bid_size + ask_size),
    }


def scan_session(
    session_date: date,
    targets: pd.DataFrame,
    cache_root: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    source_date = session_date - timedelta(days=1)
    depth_source = (
        cache_root
        / source_date.strftime("%Y_%m_%d")
        / "marketdepth.dat"
    )
    start_ticks, end_ticks = depth_bounds(session_date)
    context, raw_depth = load_cache_window(
        depth_source,
        start_ticks=start_ticks,
        end_ticks=end_ticks,
    )
    depth, effective_ticks, depth_qc = causal_depth_timestamps(
        raw_depth,
        50.0,
    )

    bid_volume: dict[int, int] = {}
    ask_volume: dict[int, int] = {}
    bid_heap: list[int] = []
    ask_heap: list[int] = []
    pointer = 0
    total = len(depth)
    latest_group_ticks: int | None = None
    current_state: tuple[int, int, int, int] | None = None
    prior_valid_state: tuple[int, int, int, int] | None = None
    last_output_state: tuple[int, int, int, int] | None = None
    last_output_ticks: int | None = None
    records: list[dict[str, object]] = []

    ordered = targets.sort_values(
        ["publish_ticks", "lb_id"]
    ).reset_index(drop=True)
    for target in ordered.itertuples(index=False):
        at_ticks = int(target.publish_ticks)
        while (
            pointer < total
            and int(effective_ticks[pointer]) <= at_ticks
        ):
            group_ticks = int(effective_ticks[pointer])
            stop = pointer + 1
            while (
                stop < total
                and int(effective_ticks[stop]) == group_ticks
            ):
                stop += 1
            for index in range(pointer, stop):
                side = int(depth[index]["side_code"])
                price = int(depth[index]["price_raw"])
                volume = int(depth[index]["volume_raw"])
                levels = bid_volume if side == 0 else ask_volume
                heap = bid_heap if side == 0 else ask_heap
                heap_price = -price if side == 0 else price
                if volume > 0:
                    if price not in levels:
                        heapq.heappush(heap, heap_price)
                    levels[price] = volume
                else:
                    levels.pop(price, None)
            current_state = valid_book_state(
                bid_volume,
                ask_volume,
                bid_heap,
                ask_heap,
            )
            if (
                current_state is not None
                and current_state != prior_valid_state
            ):
                last_output_state = current_state
                last_output_ticks = group_ticks
                prior_valid_state = current_state
            latest_group_ticks = group_ticks
            pointer = stop

        depth_age_ms = (
            (at_ticks - latest_group_ticks)
            / TICKS_PER_MILLISECOND
            if latest_group_ticks is not None
            else math.inf
        )
        feed_fresh = depth_age_ms <= 250.0
        old_accepted = bool(
            feed_fresh and last_output_state is not None
        )
        corrected_accepted = bool(
            feed_fresh and current_state is not None
        )
        old_fields = state_fields(last_output_state, "old")
        current_fields = state_fields(current_state, "current")
        saved_match = bool(
            old_accepted
            and float(old_fields["old_mid_raw"])
            == float(target.lb_mid_raw)
            and int(old_fields["old_best_bid_raw"])
            == int(target.lb_best_bid_raw)
            and int(old_fields["old_best_ask_raw"])
            == int(target.lb_best_ask_raw)
        )
        records.append(
            {
                "lb_id": target.lb_id,
                "session_date": session_date.isoformat(),
                "publish_ticks": at_ticks,
                "latest_depth_group_ticks": latest_group_ticks,
                "depth_age_ms": float(depth_age_ms),
                "old_quote_ticks": last_output_ticks,
                "quote_group_lag_ms": (
                    (at_ticks - last_output_ticks)
                    / TICKS_PER_MILLISECOND
                    if last_output_ticks is not None
                    else math.inf
                ),
                "feed_fresh_250ms": feed_fresh,
                "current_state_valid_spread_1_4": (
                    current_state is not None
                ),
                "old_pipeline_accepted": old_accepted,
                "corrected_pipeline_accepted": corrected_accepted,
                "false_acceptance_due_invalid_current_state": (
                    old_accepted and not corrected_accepted
                ),
                "stored_reference_exact_match": saved_match,
                **old_fields,
                **current_fields,
            }
        )

    return pd.DataFrame(records), {
        "session_date": session_date.isoformat(),
        "depth_source": str(depth_source),
        "depth_tick_size": float(context.tick_size),
        "depth_lot_size": float(context.lot_size),
        **depth_qc,
    }


def main() -> int:
    config = load_config(CONFIG_PATH)
    cache_root = Path(config["cache_root"])
    bursts = pd.read_csv(BURSTS_PATH)
    labels = pd.read_parquet(LABELS_PATH)
    stored = labels[
        labels["reference"].eq("MID")
        & labels["threshold_ticks"].eq(8)
        & labels["horizon_ms"].eq(5000)
        & labels["ambiguity_window_ms"].eq(250)
    ][
        [
            "lb_id",
            "session_date",
            "lb_mid_raw",
            "lb_best_bid_raw",
            "lb_best_ask_raw",
        ]
    ].copy()
    targets = bursts[
        ["lb_id", "session_date", "publish_ticks"]
    ].merge(
        stored,
        on=["lb_id", "session_date"],
        how="inner",
        validate="one_to_one",
    )
    if len(targets) != 111 or targets["session_date"].nunique() != 5:
        raise AssertionError("smoke target set is not exactly 111 LB / 5 sessions")

    parts: list[pd.DataFrame] = []
    audits: list[dict[str, object]] = []
    for session_text, part in targets.groupby(
        "session_date",
        sort=True,
    ):
        detail, audit = scan_session(
            date.fromisoformat(str(session_text)),
            part,
            cache_root,
        )
        parts.append(detail)
        audits.append(audit)
        print(
            json.dumps(
                {
                    "session_date": session_text,
                    "lbs": len(detail),
                    "false_acceptances": int(
                        detail[
                            "false_acceptance_due_invalid_current_state"
                        ].sum()
                    ),
                    "stored_reference_matches": int(
                        detail["stored_reference_exact_match"].sum()
                    ),
                }
            ),
            flush=True,
        )

    detail = pd.concat(parts, ignore_index=True)
    if not bool(detail["old_pipeline_accepted"].all()):
        raise AssertionError("old scanner did not accept all 111 stored labels")
    if not bool(detail["stored_reference_exact_match"].all()):
        raise AssertionError("old scanner did not reproduce stored references")

    false_acceptances = detail[
        "false_acceptance_due_invalid_current_state"
    ]
    by_session = (
        detail.assign(false_acceptance=false_acceptances.astype(int))
        .groupby("session_date")
        .agg(
            liquidity_bursts=("lb_id", "size"),
            false_acceptances=("false_acceptance", "sum"),
            corrected_accepted=(
                "corrected_pipeline_accepted",
                "sum",
            ),
        )
        .reset_index()
        .to_dict(orient="records")
    )
    summary = {
        "audit_id": "POST_LB_QUOTE_STATE_SMOKE_V1",
        "scope": "TECHNICAL_DEVELOPMENT_SET_ONLY",
        "sessions": int(detail["session_date"].nunique()),
        "liquidity_bursts": int(len(detail)),
        "old_pipeline_accepted": int(
            detail["old_pipeline_accepted"].sum()
        ),
        "stored_reference_exact_matches": int(
            detail["stored_reference_exact_match"].sum()
        ),
        "corrected_pipeline_accepted": int(
            detail["corrected_pipeline_accepted"].sum()
        ),
        "false_acceptances_due_invalid_current_state": int(
            false_acceptances.sum()
        ),
        "affected_lb_ids": detail.loc[
            false_acceptances,
            "lb_id",
        ].tolist(),
        "by_session": by_session,
        "regime_classes_recomputed": False,
        "non_smoke_labels_opened": False,
        "features_opened": False,
        "models_opened": False,
        "depth_audits": audits,
    }
    report = f"""# Auditoría del estado vigente de quote en smoke

Fecha: 2026-07-27

Alcance: cinco sesiones `TECHNICAL_DEVELOPMENT_SET`, 111 LB.

La reconstrucción independiente reprodujo
{summary["stored_reference_exact_matches"]}/111 referencias históricas.

Resultado:

- aceptación anterior: {summary["old_pipeline_accepted"]}/111;
- aceptación con estado vigente válido:
  {summary["corrected_pipeline_accepted"]}/111;
- falsas aceptaciones por estado vigente inválido:
  {summary["false_acceptances_due_invalid_current_state"]}.

No se recalcularon clases de régimen en esta medición y no se abrió ninguna
etiqueta no-smoke.

`INFORMATION_STATUS=QUOTE_STATE_SMOKE_IMPACT_MEASURED`
"""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    detail.to_csv(DETAIL_PATH, index=False, lineterminator="\n")
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    REPORT_PATH.write_text(report, encoding="utf-8")
    artifacts = (DETAIL_PATH, SUMMARY_PATH, REPORT_PATH)
    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "audit_id": summary["audit_id"],
                "files": {
                    path.name: {
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                    for path in artifacts
                },
            },
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
