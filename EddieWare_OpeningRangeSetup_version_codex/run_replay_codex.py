#!/usr/bin/env python3
"""Replay harness for OpeningRangeResearch_codex on a clean ATAS chart.

The chart must contain the Codex indicator and must not contain the original
exporter/execution/Telegram indicators.  Completion is detected exclusively by
the Codex heartbeat, so no Claude/base-strategy result can shorten the replay.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path


SOURCE_RUNTIME = Path(
    r"C:\Users\k_99_\Desktop\codding\OpeningRangeSetup\EddiewareOpeningRangeSetup\EddiewareOpeningRangeSetup"
)
DATA_DIR = Path(__file__).resolve().parent / "research_data_codex"
sys.path.insert(0, str(SOURCE_RUNTIME))
import replay_sync_runner_common_after_sync as replay  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Single NY date YYYY-MM-DD")
    parser.add_argument("--start", default="2025-03-10")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--timeout", type=int, default=150)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--clean-chart-confirmed",
        action="store_true",
        help="Required: confirms the chart has no original exporter/Telegram indicators.",
    )
    return parser.parse_args()


def trading_dates(start: str, end: str) -> list[str]:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    output = []
    current = first
    while current <= last:
        if current.weekday() < 5:
            output.append(current.isoformat())
        current += timedelta(days=1)
    return output


def status_path(date_iso: str) -> Path:
    return DATA_DIR / f"codex_status_{date_iso}.txt"


def candidate_path(date_iso: str) -> Path:
    return DATA_DIR / f"opening_range_candidates_{date_iso}_codex.csv"


def completed_after(date_iso: str, started_at: float) -> bool:
    path = status_path(date_iso)
    try:
        return path.stat().st_mtime >= started_at and "complete=1" in path.read_text(encoding="utf-8")
    except OSError:
        return False


def run_date(date_iso: str, timeout: int, force: bool) -> bool:
    status = status_path(date_iso)
    candidates = candidate_path(date_iso)
    if not force and completed_after(date_iso, 0) and candidates.exists():
        print(f"SKIP {date_iso}: Codex output already complete")
        return True
    if force:
        status.unlink(missing_ok=True)
        candidates.unlink(missing_ok=True)

    window, from_box, to_box, play, stop = replay.get_replay_controls()
    replay.configure_replay_range(
        from_box,
        to_box,
        date_iso,
        replay_from_time="09:20:00",
        replay_to_time="09:46:00",
    )
    window.set_focus()
    time.sleep(0.4)
    started_at = time.time()
    play.click_input()
    print(f"PLAY {date_iso}")

    deadline = started_at + timeout
    last_print = -1
    while time.time() < deadline:
        if completed_after(date_iso, started_at):
            replay.click_stop(stop)
            print(f"OK   {date_iso}: Codex heartbeat complete")
            return True
        elapsed = int(time.time() - started_at)
        if elapsed != last_print and elapsed % 10 == 0:
            print(f"WAIT {date_iso}: {elapsed}s")
            last_print = elapsed
        time.sleep(0.25)

    replay.click_stop(stop)
    print(f"FAIL {date_iso}: no Codex completion heartbeat")
    return False


def main() -> int:
    args = parse_args()
    if not args.clean_chart_confirmed:
        raise SystemExit(
            "Refusing to replay: first use a clean NQ 1-minute chart containing only "
            "Opening Range Research Codex, then pass --clean-chart-confirmed."
        )
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dates = [args.date] if args.date else trading_dates(args.start, args.end)
    failures = []
    for date_iso in dates:
        try:
            if not run_date(date_iso, args.timeout, args.force):
                failures.append(date_iso)
        except Exception as exc:
            replay.click_stop()
            print(f"ERROR {date_iso}: {exc}")
            failures.append(date_iso)
    print(f"Finished: {len(dates) - len(failures)}/{len(dates)} complete")
    if failures:
        print("Failures: " + ", ".join(failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
