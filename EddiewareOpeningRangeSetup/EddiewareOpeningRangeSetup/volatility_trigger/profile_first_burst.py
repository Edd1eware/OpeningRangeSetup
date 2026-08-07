from __future__ import annotations

import cProfile
import io
import pstats
from datetime import date
from pathlib import Path

from run_research import CONFIG_PATH, load_session
from src.vt_core import (
    TICKS_PER_MILLISECOND,
    TICKS_PER_SECOND,
    compute_candidate_features,
    compute_outcomes,
    contiguous_trade_ticks,
    detect_liquidity_bursts,
    load_config,
    profile_snapshots,
)


def main() -> int:
    config = load_config(CONFIG_PATH)
    session_date = date(2022, 8, 1)
    _, trades, _ = load_session(
        session_date,
        Path(config["cache_root"]),
    )
    burst = detect_liquidity_bursts(
        trades,
        session_date,
        config["detector"],
    )[0]
    offsets = range(
        0,
        int(config["candidate_max_ms"]) + 1,
        int(config["candidate_grid_ms"]),
    )
    candidate_times = [
        burst.publish_ticks + offset * TICKS_PER_MILLISECOND
        for offset in offsets
    ]
    trade_ticks = contiguous_trade_ticks(trades)
    profiles = profile_snapshots(
        trades,
        candidate_times
        + [
            candidate_ticks - 30 * TICKS_PER_SECOND
            for candidate_ticks in candidate_times
        ],
        trade_ticks=trade_ticks,
    )

    def work() -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for candidate_ticks in candidate_times:
            for direction in config["candidate_directions"]:
                result.append(
                    {
                        **compute_candidate_features(
                            trades,
                            burst,
                            candidate_ticks,
                            int(direction),
                            profiles,
                            trade_ticks=trade_ticks,
                        ),
                        **compute_outcomes(
                            trades,
                            candidate_ticks,
                            int(direction),
                            config,
                            trade_ticks=trade_ticks,
                        ),
                    }
                )
        return result

    profiler = cProfile.Profile()
    profiler.enable()
    rows = work()
    profiler.disable()
    output = io.StringIO()
    pstats.Stats(profiler, stream=output).sort_stats(
        "cumtime"
    ).print_stats(40)
    print(f"rows={len(rows)}")
    print(output.getvalue())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
