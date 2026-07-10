#!/usr/bin/env python3
"""Reanuda la recaptura 2022+2024 con BookRecorder donde haya quedado.

Uso manual (ATAS abierto, Replay visible, DOM activado, chart NQ 1-min con
Volume_Profile_Eddieware + ATRAPADOS Book Recorder):

    python -u resume_recapture.py

Regenera la lista de fechas pendientes (las que NO tienen mbp_*.csv fresco de la campaña,
corte 2026-07-10 07:00) y lanza el runner solo con esas. Se puede cortar y relanzar las
veces que haga falta: nunca repite lo ya grabado, nunca borra nada.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from lvn_OR_strategy_replay import us_market_holidays

BOOK = Path(r"C:\Users\k_99_\Desktop\codding\data_footprint_generator\book_recordings")
CAMPAIGN_START = datetime(2026, 7, 10, 7, 0)
RANGES = [("2022-04-04", "2022-11-04"), ("2024-03-10", "2024-11-01")]
OUTPUT = "outputs/lvn_or_strategy_replay/lvn_retest_bookrec_2022_2024.xlsx"


def weekdays(start: str, end: str) -> list[str]:
    out = []
    day = date.fromisoformat(start)
    finish = date.fromisoformat(end)
    while day <= finish:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def main() -> int:
    dates: list[str] = []
    holidays: set[str] = set()
    for start, end in RANGES:
        dates += weekdays(start, end)
        holidays |= us_market_holidays(int(start[:4]))
    dates = [d for d in dates if d not in holidays]
    pending = []
    for d in dates:
        mbp = BOOK / f"mbp_{d}_NY.csv"
        if not (mbp.exists() and datetime.fromtimestamp(mbp.stat().st_mtime) >= CAMPAIGN_START):
            pending.append(d)
    print(f"hechas: {len(dates) - len(pending)}/{len(dates)} | pendientes: {len(pending)}")
    if not pending:
        print("Nada pendiente: la recaptura está COMPLETA.")
        return 0
    command = [sys.executable, "-u", "lvn_OR_strategy_replay.py", "--run", "--force",
               "--dates", *pending, "--output", OUTPUT]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
