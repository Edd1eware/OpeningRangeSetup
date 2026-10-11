"""Shared config for the NQ Opening Range Breakout L2 research project."""
from __future__ import annotations

import os

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DATASET = "GLBX.MDP3"
SYMBOL = "NQ.c.0"          # front-month continuous, rolled by volume
STYPE_IN = "continuous"

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# --- research windows, in ET clock time -------------------------------------
# ohlcv-1s covers the whole RTH session so we can measure the day's outcome.
# L2 schemas are restricted to the open to keep the bill sane.
WINDOWS: dict[str, tuple[time, time]] = {
    "ohlcv-1s": (time(8, 0), time(16, 15)),
    "mbp-10":   (time(9, 25), time(10, 30)),
    "mbo":      (time(9, 30), time(10, 0)),
    "trades":   (time(9, 25), time(10, 30)),
    "definition": (time(9, 0), time(9, 1)),
}

OR_OPEN = time(9, 30)        # cash open
OR_MINUTES_GRID = (1, 5, 15, 30)   # opening-range lengths to evaluate

ROOT = Path(__file__).resolve().parent.parent
# ORB_DATA_ROOT lets the smoke test run the whole pipeline on synthetic data
# without touching the real downloads.
DATA = Path(os.environ.get("ORB_DATA_ROOT", str(ROOT / "data")))
LOGS = ROOT / "logs"
MANIFEST = LOGS / "download_manifest.csv"

# CME equity-index full holidays (no RTH session). Half days still trade.
CME_HOLIDAYS = {
    "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31",
    "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24",
    "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20",
    "2022-07-04", "2022-09-05", "2022-11-24", "2022-12-26",
    "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29",
    "2023-06-19", "2023-07-04", "2023-09-04", "2023-11-23", "2023-12-25",
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
    "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07",
}


def ny_window_utc(day: date, start: time, end: time) -> tuple[str, str]:
    """Convert an ET clock window on `day` to UTC ISO strings (DST-safe)."""
    s = datetime.combine(day, start, tzinfo=NY).astimezone(UTC)
    e = datetime.combine(day, end, tzinfo=NY).astimezone(UTC)
    return s.isoformat().replace("+00:00", "Z"), e.isoformat().replace("+00:00", "Z")


def session_days(start: date, end: date, dst_only: bool = True) -> list[date]:
    """Weekdays between start and end, minus CME holidays, EDT-only by default."""
    import pandas as pd
    days = pd.bdate_range(start, end).date
    out = [d for d in days if d.isoformat() not in CME_HOLIDAYS]
    return [d for d in out if is_dst(d)] if dst_only else out

def is_dst(day: date) -> bool:
    """True if `day` falls inside US Eastern daylight saving time (EDT, UTC-4).

    Research is restricted to EDT days for now so the UTC offset of the 09:30
    open is constant at 13:30Z. Mixing EST days shifts the open to 14:30Z and
    silently misaligns any feature keyed on a UTC clock time.
    """
    return datetime.combine(day, time(12, 0), tzinfo=NY).dst() != timedelta(0)



def out_path(schema: str, day: date) -> Path:
    folder = DATA / schema.replace("-", "")
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"NQ_{schema}_{day.isoformat()}.dbn.zst"

CREDENTIALS = ROOT / "credentials" / "databento.env"


def load_api_key() -> str:
    """Read DATABENTO_API_KEY from credentials/databento.env into the env.

    Keeps the key out of every script and out of the shell history. The file is
    gitignored; the committed template is databento.env.example.
    """
    if CREDENTIALS.exists():
        for line in CREDENTIALS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    # a key pasted into NUEVA_API_KEY.txt wins: it is the newer one
    dropin = CREDENTIALS.parent / "NUEVA_API_KEY.txt"
    if dropin.exists():
        for line in dropin.read_text(encoding="utf-8").splitlines():
            cand = line.strip().split("=")[-1].strip().strip("'\"")
            if cand.startswith("db-") and len(cand) >= 20:
                os.environ["DATABENTO_API_KEY"] = cand
                break
    key = os.environ.get("DATABENTO_API_KEY", "")
    if not key.startswith("db-"):
        raise SystemExit(
            f"no valid DATABENTO_API_KEY. put it in {CREDENTIALS} "
            "(see databento.env.example)")
    return key


def masked_key() -> str:
    k = load_api_key()
    return f"{k[:6]}...{k[-3:]}"
