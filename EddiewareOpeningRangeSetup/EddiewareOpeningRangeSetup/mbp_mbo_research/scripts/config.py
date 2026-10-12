"""Shared config for the NQ Opening Range Breakout L2 research project."""
from __future__ import annotations

import os

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DATASET = "GLBX.MDP3"
# NQ.v.0 = continuous front month rolled by VOLUME. Do not use NQ.c.0: it rolls
# on the calendar, so on expiry Friday it still points at the dying contract
# (verified 2026-09-18: NQ.c.0 = 0 trades, NQ.v.0 = 13,014 trades in 5 min).
# The series jumps by the calendar spread at each roll, so never measure an
# overnight gap across one without adjusting.
SYMBOL = "NQ.v.0"
STYPE_IN = "continuous"

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# --- research windows, in ET clock time -------------------------------------
# ohlcv-1s covers the whole RTH session so we can measure the day's outcome.
# L2 schemas are restricted to the open to keep the bill sane.
# A window whose start equals its end means the FULL calendar day in ET
# (00:00 -> next 00:00), which for 1s bars is cheap and removes any doubt about
# what sits outside the cash session.
FULL_DAY = (time(0, 0), time(0, 0))

WINDOWS: dict[str, tuple[time, time]] = {
    "ohlcv-1s": FULL_DAY,
    "mbp-10":   (time(9, 25), time(10, 30)),
    "mbo":      (time(9, 30), time(10, 0)),
    "trades":   (time(9, 25), time(10, 30)),
    "definition": (time(9, 0), time(9, 1)),
}

# --- setup definition (user spec, treated as ground truth) ------------------
OR_OPEN = time(9, 30)          # cash open; the OR is the single 09:30 M1 candle
OR_MINUTES = 1
ENTRY_FROM = time(9, 31)       # first minute that may trigger an entry
ENTRY_TO = time(9, 39)         # last minute that may trigger an entry
RR = 1.0                       # TP == SL, so breakeven WR is 50%
MOVE_MIN_TICKS = 30            # no setup below this target size
MOVE_MAX_TICKS = 120           # none above it either
BRACKET_TICKS = (30, 40, 50, 60, 80, 100, 120)   # TP = SL, inside the band
REQUIRE_BODY_BREAK = True      # the M1 CLOSE must clear the level, not the wick
REQUIRE_VWAP_ALIGN = True      # long only above VWAP, short only below

# How the entry is taken once a signal prints. All three are measured so the
# choice is made on EV and fill rate, not on taste.
#   market      : next 1s open after the breaking M1 closes. Always fills, but
#                 pays whatever extension that candle ran.
#   limit_level : resting limit at the broken OR level, valid to LIMIT_VALID_TO.
#                 Best price, but some signals never come back and never fill.
#   chase_<n>   : market, only if the M1 closed within n ticks of the level.
ENTRY_MODES = ("market", "limit_level", "chase_10", "chase_15", "chase_20",
               "chase_30", "chase_40")
LIMIT_VALID_TO = time(9, 40)   # a limit still unfilled by then is cancelled

ROOT = Path(__file__).resolve().parent.parent
# Data lives OUTSIDE this folder: the project sits in a git repo and the DBN
# files run to tens of GB. ORB_DATA_ROOT overrides it, which is also how the
# smoke test drives the pipeline on synthetic data.
DATA_DEFAULT = Path("C:/Users/k_99_/Desktop/codding/MBP_MBO")
DATA = Path(os.environ.get("ORB_DATA_ROOT", str(DATA_DEFAULT)))
LOGS = DATA / "logs"
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
    """Convert an ET clock window on `day` to UTC ISO strings (DST-safe).

    start == end is the full-day sentinel: 00:00 ET to 00:00 ET the next day.
    """
    s = datetime.combine(day, start, tzinfo=NY).astimezone(UTC)
    if start == end:
        e = (datetime.combine(day, start, tzinfo=NY)
             + timedelta(days=1)).astimezone(UTC)
        return (s.isoformat().replace("+00:00", "Z"),
                e.isoformat().replace("+00:00", "Z"))
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
