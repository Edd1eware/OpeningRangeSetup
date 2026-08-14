from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import struct
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import MetaTrader5 as mt5


NY = ZoneInfo("America/New_York")
UTC = timezone.utc
DOTNET_UNIX_EPOCH_TICKS = 621355968000000000
ATAS_SCALE_RE = re.compile(r"VolumeCandles_m1_scale_(\d+)_False\.dat$")


@dataclass(frozen=True)
class Bar:
    time_ny: datetime
    open: float
    high: float
    low: float
    close: float
    bid: int = 0
    ask: int = 0
    between: int = 0
    ticks: int = 0
    min_delta: int = 0
    max_delta: int = 0
    # (price, bid, ask, between, ticks), frozen when the M1 candle closes.
    price_levels: tuple[tuple[float, int, int, int, int], ...] = ()


@dataclass(frozen=True)
class Pivot:
    market: str
    kind: str
    time_ny: datetime
    price: float
    atr: float
    swing_atr: float
    reaction_atr: float
    # A 2x2 pivot is only knowable once its two right-hand bars have closed, so
    # this is the first minute at which the pivot may be used as evidence.
    known_at_ny: datetime | None = None


@dataclass(frozen=True)
class Event:
    session_date_ny: str
    leader: str
    lagger: str
    pivot_kind: str
    leader_time_ny: str
    detection_time_ny: str
    lagger_time_ny: str
    delay_minutes: int | None
    lagger_confirmed_within_window: bool
    leader_price: float
    lagger_price: float
    leader_swing_atr: float
    lagger_swing_atr: float
    leader_reaction_atr: float
    lagger_reaction_atr: float
    occurrence_hour_ny: int


def is_dst(value: datetime) -> bool:
    aware = value if value.tzinfo else value.replace(tzinfo=NY)
    return bool(aware.astimezone(NY).dst())


def dotnet_ticks_to_utc(ticks: int) -> datetime:
    unix_ticks = ticks - DOTNET_UNIX_EPOCH_TICKS
    seconds, remainder = divmod(unix_ticks, 10_000_000)
    return datetime.fromtimestamp(seconds, UTC).replace(microsecond=remainder // 10)


def decode_atas_cache_file(path: Path) -> list[Bar]:
    match = ATAS_SCALE_RE.match(path.name)
    if not match:
        return []
    price_scale = int(match.group(1))
    payload = path.read_bytes()
    if len(payload) < 9 or payload[:4] != b"ATAS":
        return []

    bars: list[Bar] = []
    cursor = 4
    tick_size = 0.0
    while cursor + 4 <= len(payload):
        chunk_size = struct.unpack_from("<I", payload, cursor)[0]
        chunk_start = cursor + 4
        chunk_end = chunk_start + chunk_size
        if chunk_size < 1 or chunk_end > len(payload):
            raise ValueError(f"Chunk ATAS inválido en {path}: offset={cursor}, size={chunk_size}")
        message_type = payload[chunk_start]
        if message_type == 91:  # contexto de almacenamiento
            tick_size = struct.unpack_from("<d", payload, chunk_start + 1)[0]
        elif message_type in (90, 133):  # lote inicial o lote de velas
            record_cursor = chunk_start
            if message_type == 90:
                tick_size = struct.unpack_from("<d", payload, chunk_start + 1)[0]
                record_cursor = chunk_start + 17
            if tick_size <= 0:
                raise ValueError(f"Tick size ausente en {path}")

            while record_cursor < chunk_end:
                if payload[record_cursor] != 133:
                    raise ValueError(
                        f"Marcador de vela ATAS inválido en {path}: offset={record_cursor}"
                    )
                fixed = record_cursor + 1
                (
                    open_ticks,
                    _close_ticks,
                    open_price,
                    close_price,
                    min_delta,
                    max_delta,
                    _open_interest,
                    _min_open_interest,
                    _max_open_interest,
                ) = struct.unpack_from("<qqiiiiIII", payload, fixed)
                entry_size = struct.unpack_from("<H", payload, fixed + 44)[0]
                entry_count = struct.unpack_from("<I", payload, fixed + 46)[0]
                if entry_size != 20 or entry_count > 100_000:
                    raise ValueError(
                        f"Grupo de precios ATAS inválido en {path}: "
                        f"entry_size={entry_size}, count={entry_count}"
                    )

                levels: list[tuple[int, int, int, int, int]] = []
                for entry_index in range(entry_count):
                    entry_offset = fixed + 50 + entry_index * entry_size
                    levels.append(struct.unpack_from("<iiiii", payload, entry_offset))
                multiplier = tick_size * price_scale
                prices = [level[0] for level in levels]
                high_price = max(prices) if prices else max(open_price, close_price)
                low_price = min(prices) if prices else min(open_price, close_price)
                stamp = dotnet_ticks_to_utc(open_ticks).astimezone(NY)
                total_bid = sum(level[1] for level in levels)
                total_ask = sum(level[2] for level in levels)
                total_between = sum(level[3] for level in levels)
                total_ticks = sum(level[4] for level in levels)
                bars.append(
                    Bar(
                        stamp,
                        open_price * multiplier,
                        high_price * multiplier,
                        low_price * multiplier,
                        close_price * multiplier,
                        total_bid,
                        total_ask,
                        total_between,
                        total_ticks,
                        min_delta,
                        max_delta,
                        tuple(
                            (
                                level[0] * multiplier,
                                level[1],
                                level[2],
                                level[3],
                                level[4],
                            )
                            for level in levels
                        ),
                    )
                )
                record_cursor = fixed + 50 + entry_count * entry_size
        cursor = chunk_end

    return bars


def load_atas_bars(
    root: Path | None,
    cache_root: Path | None,
    start: datetime,
    end: datetime,
) -> dict[str, list[Bar]]:
    sessions: dict[str, dict[datetime, Bar]] = defaultdict(dict)
    paths: set[Path] = set()
    if root:
        paths.update(root.glob("netflow_fp_bars_*_m1.csv"))
        paths.update(root.glob("atas_nq_m1_*.csv"))
    for path in sorted(paths):
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            required = {"bar_time_ny", "open", "high", "low", "close"}
            if not required.issubset(reader.fieldnames or ()):
                continue
            for row in reader:
                try:
                    stamp = datetime.fromisoformat(row["bar_time_ny"]).replace(tzinfo=NY)
                    bar = Bar(
                        stamp,
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                if start <= stamp <= end and is_dst(stamp):
                    sessions[stamp.date().isoformat()][stamp] = bar

    if cache_root:
        for path in sorted(cache_root.glob("*/VolumeCandles_m1_scale_*_False.dat")):
            folder = path.parent.name.replace("_", "-")
            try:
                cache_day = datetime.fromisoformat(folder).date()
            except ValueError:
                continue
            if cache_day < start.date() - timedelta(days=1) or cache_day > end.date():
                continue
            for bar in decode_atas_cache_file(path):
                if start <= bar.time_ny <= end and is_dst(bar.time_ny):
                    sessions[bar.time_ny.date().isoformat()][bar.time_ny] = bar
    return {day: sorted(values.values(), key=lambda item: item.time_ny) for day, values in sessions.items()}


class BrokerClock:
    """
    MT5 delivers times in BROKER SERVER time packed as a POSIX integer that looks
    like UTC. Reading it as UTC fabricates exactly the lead-lag this study tries
    to measure, so the integer is unpacked back into the server's wall clock and
    localised through the broker's own calendar.

    Two calendars are supported because getting this wrong is worth exactly one
    hour on the ~3 weeks per year when the US and Europe disagree on DST, and the
    pivot rule selects those minutes disproportionately:

      "us"     - base UTC+2, UTC+3 while NEW YORK is on DST. This is the usual FX
                 broker convention ("GMT+2/+3 switching with New York").
      "europe" - a real European zone such as Europe/Athens.

    Which one is right is decided empirically by the alignment scan, never assumed.
    """

    def __init__(self, calendar: str, base_offset: int = 2, dst_offset: int = 3) -> None:
        self.calendar = calendar
        self.base_offset = base_offset
        self.dst_offset = dst_offset
        self.zone = ZoneInfo(calendar) if calendar not in ("us",) else None

    def __str__(self) -> str:
        return (
            self.calendar if self.zone
            else f"UTC+{self.base_offset}/+{self.dst_offset} con calendario de Nueva York"
        )

    def offset_for_utc(self, moment: datetime) -> int:
        return self.dst_offset if moment.astimezone(NY).dst() else self.base_offset

    def wall_to_utc(self, seconds: int) -> datetime:
        wall = datetime.fromtimestamp(seconds, UTC).replace(tzinfo=None)
        if self.zone is not None:
            return wall.replace(tzinfo=self.zone).astimezone(UTC)
        # The offset depends on the instant we are trying to recover, so both
        # candidates are tested and the self-consistent one wins. During the
        # one ambiguous hour per year the later offset is used.
        for offset in (self.dst_offset, self.base_offset):
            candidate = (wall - timedelta(hours=offset)).replace(tzinfo=UTC)
            if self.offset_for_utc(candidate) == offset:
                return candidate
        return (wall - timedelta(hours=self.dst_offset)).replace(tzinfo=UTC)

    def utc_to_wall(self, moment: datetime) -> datetime:
        if self.zone is not None:
            return moment.astimezone(self.zone).replace(tzinfo=None)
        return (moment.astimezone(UTC) + timedelta(hours=self.offset_for_utc(moment))).replace(
            tzinfo=None
        )


def verify_broker_clock(symbol: str, clock: BrokerClock) -> float:
    """
    Cross-checks the declared broker calendar against a live tick. A live tick
    only proves the offset for today, so it is a necessary check, never a
    sufficient one: the per-session alignment scan is what validates history.
    """
    tick = mt5.symbol_info_tick(symbol)
    if tick is None or not tick.time:
        raise RuntimeError(f"No hay tick de {symbol} para verificar el reloj: {mt5.last_error()}")
    residual = (clock.wall_to_utc(int(tick.time)) - datetime.now(UTC)).total_seconds() / 3600.0
    raw = (
        datetime.fromtimestamp(int(tick.time), UTC).replace(tzinfo=None)
        - datetime.now(UTC).replace(tzinfo=None)
    ).total_seconds() / 3600.0
    print(f"[mt5] offset crudo servidor-UTC = {raw:+.3f} h  (reloj declarado: {clock})")
    print(f"[mt5] residual tras convertir  = {residual:+.4f} h  (solo valida HOY)")
    if abs(residual) > 0.1:
        raise RuntimeError(
            f"El reloj '{clock}' no explica el servidor (residual {residual:+.3f} h)."
        )
    return residual


def load_mt5_bars(
    terminal: Path,
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    broker_calendar: str = "us",
) -> dict[datetime, Bar]:
    if not mt5.initialize(path=str(terminal)):
        raise RuntimeError(f"MT5 initialize fallo: {mt5.last_error()}")
    try:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"No se pudo seleccionar {symbol}: {mt5.last_error()}")

        clock = BrokerClock(broker_calendar)
        verify_broker_clock(symbol, clock)

        # copy_rates_range interprets its bounds in server time, so the request is
        # expressed in the server wall clock (kept UTC-aware per the API contract)
        # and padded a day on each side so the offset cannot truncate edge sessions.
        rates = mt5.copy_rates_range(
            symbol,
            mt5.TIMEFRAME_M1,
            clock.utc_to_wall(start.astimezone(UTC) - timedelta(days=1)).replace(tzinfo=UTC),
            clock.utc_to_wall(end.astimezone(UTC) + timedelta(days=1)).replace(tzinfo=UTC),
        )
        if rates is None:
            raise RuntimeError(f"CopyRates fallo: {mt5.last_error()}")
        result: dict[datetime, Bar] = {}
        for rate in rates:
            stamp = clock.wall_to_utc(int(rate["time"])).astimezone(NY)
            if not (start <= stamp <= end) or not is_dst(stamp):
                continue
            result[stamp] = Bar(
                stamp,
                float(rate["open"]),
                float(rate["high"]),
                float(rate["low"]),
                float(rate["close"]),
            )
        return result
    finally:
        mt5.shutdown()


def diagnose_alignment_by_session(
    atas_sessions: dict[str, list[Bar]],
    mt5_bars: dict[datetime, Bar],
    *,
    max_shift_minutes: int = 90,
) -> dict[str, object]:
    """
    Per-session return correlation across a WIDE shift range.

    An annual average hides the failure mode that matters here: if the broker
    clock is wrong for a handful of sessions the yearly peak still lands on zero,
    while the pivot rule concentrates its events precisely on the broken days. A
    +-5 minute scan can never see a 60 minute error, so the range must exceed an
    hour and the check must be per session.
    """
    import numpy as np

    per_session: dict[str, int] = {}
    rho_at_zero: dict[str, float] = {}
    for day, bars in sorted(atas_sessions.items()):
        stamps = [bar.time_ny for bar in bars if bar.time_ny in mt5_bars]
        if len(stamps) < 120:
            continue
        base = min(stamps)
        grid_size = int((max(stamps) - base).total_seconds() // 60) + 1
        if grid_size < 120 or grid_size > 3000:
            continue
        atas_grid = np.full(grid_size, np.nan)
        cfd_grid = np.full(grid_size, np.nan)
        atas_by_time = {bar.time_ny: bar for bar in bars}
        for stamp in stamps:
            slot = int((stamp - base).total_seconds() // 60)
            atas_grid[slot] = atas_by_time[stamp].close
            cfd_grid[slot] = mt5_bars[stamp].close
        atas_returns = np.diff(atas_grid)
        cfd_returns = np.diff(cfd_grid)

        best_shift, best_rho = 0, -np.inf
        zero_rho = np.nan
        span = min(max_shift_minutes, len(atas_returns) // 3)
        for shift in range(-span, span + 1):
            if shift >= 0:
                left, right = atas_returns[: len(atas_returns) - shift], cfd_returns[shift:]
            else:
                left, right = atas_returns[-shift:], cfd_returns[: len(cfd_returns) + shift]
            mask = np.isfinite(left) & np.isfinite(right)
            if mask.sum() < 60:
                continue
            a, b = left[mask], right[mask]
            if a.std() == 0 or b.std() == 0:
                continue
            rho = float(np.corrcoef(a, b)[0, 1])
            if shift == 0:
                zero_rho = rho
            if rho > best_rho:
                best_rho, best_shift = rho, shift
        per_session[day] = best_shift
        rho_at_zero[day] = round(zero_rho, 4) if zero_rho == zero_rho else None

    offenders = {day: shift for day, shift in per_session.items() if shift != 0}
    distribution = Counter(per_session.values())
    return {
        "sessions_scanned": len(per_session),
        "max_shift_minutes": max_shift_minutes,
        "best_shift_distribution": {str(k): v for k, v in sorted(distribution.items())},
        "sessions_misaligned": len(offenders),
        "misaligned_sessions": dict(sorted(offenders.items())),
        "all_sessions_aligned": not offenders,
        "median_rho_at_zero": round(
            statistics.median([v for v in rho_at_zero.values() if v is not None]), 4
        ) if rho_at_zero else None,
    }


def diagnose_alignment(
    atas_sessions: dict[str, list[Bar]],
    mt5_bars: dict[datetime, Bar],
    *,
    minute_shifts: range = range(-5, 6),
) -> dict[str, object]:
    """
    Correlates M1 close-to-close returns of both feeds across integer-minute
    shifts. If the two grids are aligned the peak sits at shift 0; a peak
    anywhere else means the join itself is manufacturing the lead-lag and no
    downstream number is interpretable.
    """
    atas_by_time = {bar.time_ny: bar for day in atas_sessions.values() for bar in day}
    common = sorted(set(atas_by_time) & set(mt5_bars))
    pairs: list[tuple[datetime, float, float]] = []
    for stamp in common:
        previous = stamp - timedelta(minutes=1)
        if previous not in atas_by_time or previous not in mt5_bars:
            continue
        pairs.append(
            (
                stamp,
                atas_by_time[stamp].close - atas_by_time[previous].close,
                mt5_bars[stamp].close - mt5_bars[previous].close,
            )
        )

    atas_returns = {stamp: value for stamp, value, _ in pairs}
    cfd_returns = {stamp: value for stamp, _, value in pairs}

    def correlate(shift_minutes: int) -> tuple[int, float]:
        xs: list[float] = []
        ys: list[float] = []
        delta = timedelta(minutes=shift_minutes)
        for stamp, atas_value, _ in pairs:
            shifted = stamp + delta
            if shifted in cfd_returns:
                xs.append(atas_value)
                ys.append(cfd_returns[shifted])
        if len(xs) < 100:
            return len(xs), float("nan")
        mean_x = statistics.fmean(xs)
        mean_y = statistics.fmean(ys)
        num = sum((a - mean_x) * (b - mean_y) for a, b in zip(xs, ys))
        den = math.sqrt(
            sum((a - mean_x) ** 2 for a in xs) * sum((b - mean_y) ** 2 for b in ys)
        )
        return len(xs), (num / den if den else float("nan"))

    profile: dict[str, dict[str, float | int]] = {}
    best_shift = 0
    best_rho = float("-inf")
    for shift_minutes in minute_shifts:
        count, rho = correlate(shift_minutes)
        profile[f"{shift_minutes:+d}m"] = {"n": count, "rho": round(rho, 6) if rho == rho else None}
        if rho == rho and rho > best_rho:
            best_rho = rho
            best_shift = shift_minutes

    # A positive shift means the CFD return that best matches NQ arrives LATER,
    # i.e. NQ leads. Negative means the CFD moved first.
    return {
        "pairs_compared": len(pairs),
        "shift_profile_rho": profile,
        "best_shift_minutes": best_shift,
        "best_rho": round(best_rho, 6) if best_rho > float("-inf") else None,
        "aligned_at_zero": best_shift == 0,
        "interpretation": (
            "grids alineadas (pico en 0)" if best_shift == 0
            else ("el CFD va ADELANTADO en el reloj" if best_shift < 0
                  else "el CFD va ATRASADO en el reloj")
        ),
    }


def is_contiguous(bars: list[Bar], first: int, last: int) -> bool:
    return all(
        int((bars[index].time_ny - bars[index - 1].time_ny).total_seconds()) == 60
        for index in range(first + 1, last + 1)
    )


def atr_at(bars: list[Bar], index: int, period: int = 14) -> float:
    values: list[float] = []
    first = max(1, index - period + 1)
    for cursor in range(first, index + 1):
        previous = bars[cursor - 1]
        current = bars[cursor]
        if int((current.time_ny - previous.time_ny).total_seconds()) != 60:
            values.clear()
            continue
        values.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return statistics.fmean(values) if values else 0.0


def detect_pivots(
    bars: list[Bar],
    market: str,
    *,
    strength: int = 2,
    swing_lookback: int = 8,
    minimum_swing_atr: float = 3.00,
    minimum_reaction_atr: float = 1.00,
) -> list[Pivot]:
    pivots: list[Pivot] = []
    for index in range(max(strength, swing_lookback), len(bars) - strength):
        if not is_contiguous(bars, index - swing_lookback, index + strength):
            continue
        atr = atr_at(bars, index)
        if atr <= 1e-9:
            continue
        current = bars[index]
        left = bars[index - strength : index]
        right = bars[index + 1 : index + strength + 1]

        is_low = (
            all(current.low <= item.low for item in left)
            and all(current.low < item.low for item in right)
            and any(current.low < item.low for item in left)
        )
        is_high = (
            all(current.high >= item.high for item in left)
            and all(current.high > item.high for item in right)
            and any(current.high > item.high for item in left)
        )

        prior = bars[index - swing_lookback : index]
        if is_low:
            swing = (max(item.high for item in prior) - current.low) / atr
            reaction = (max(item.high for item in right) - current.low) / atr
            if swing >= minimum_swing_atr and reaction >= minimum_reaction_atr:
                pivots.append(Pivot(
                    market, "INFERIOR", current.time_ny, current.low, atr, swing, reaction,
                    bars[index + strength].time_ny,
                ))
        if is_high:
            swing = (current.high - min(item.low for item in prior)) / atr
            reaction = (current.high - min(item.low for item in right)) / atr
            if swing >= minimum_swing_atr and reaction >= minimum_reaction_atr:
                pivots.append(Pivot(
                    market, "SUPERIOR", current.time_ny, current.high, atr, swing, reaction,
                    bars[index + strength].time_ny,
                ))
    return pivots


def equivalent_pivots(
    candidates: list[Pivot],
    leader: Pivot,
    *,
    first_time: datetime,
    last_time: datetime,
    expected_price: float,
    level_tolerance_atr: float = 1.50,
    known_by: datetime | None = None,
) -> list[Pivot]:
    matches: list[Pivot] = []
    for candidate in candidates:
        if candidate.kind != leader.kind or not first_time <= candidate.time_ny <= last_time:
            continue
        # A lagger pivot cannot count as "already there" if its own 2x2 was not
        # yet confirmed at the moment the decision is taken.
        if (
            known_by is not None
            and candidate.known_at_ny is not None
            and candidate.known_at_ny > known_by
        ):
            continue
        swing_ratio = candidate.swing_atr / max(leader.swing_atr, 1e-9)
        reaction_ratio = candidate.reaction_atr / max(leader.reaction_atr, 1e-9)
        level_distance_atr = abs(candidate.price - expected_price) / max(candidate.atr, 1e-9)
        if (
            0.60 <= swing_ratio <= 1.80
            and reaction_ratio >= 0.50
            and level_distance_atr <= level_tolerance_atr
        ):
            matches.append(candidate)
    return matches


def detect_lead_events(
    atas: list[Pivot],
    cfd: list[Pivot],
    atas_bars: list[Bar],
    cfd_bars: list[Bar],
    common_times: set[datetime],
    *,
    minimum_delay: int = 3,
    maximum_delay: int = 8,
    minimum_swing_atr: float = 3.0,
    minimum_reaction_atr: float = 1.0,
) -> list[Event]:
    events: list[Event] = []
    atas_close = {item.time_ny: item.close for item in atas_bars}
    cfd_close = {item.time_ny: item.close for item in cfd_bars}
    for leader_market, lagger_market, leader_pivots, lagger_pivots in (
        ("ATAS L2", "CFD MT5", atas, cfd),
        ("CFD MT5", "ATAS L2", cfd, atas),
    ):
        for leader in leader_pivots:
            if leader.swing_atr < minimum_swing_atr or leader.reaction_atr < minimum_reaction_atr:
                continue
            detection_time = leader.time_ny + timedelta(minutes=minimum_delay)
            if detection_time not in common_times:
                continue
            # NQ and USTEC quote the same index on a different base, so the level
            # maps through an ADDITIVE basis frozen at the pivot minute, never a
            # multiplicative ratio. See CLAUDE_CONTEXTO_NQ_LIDERA_DESFASAMIENTO.md.
            basis_cfd_minus_atas = cfd_close[leader.time_ny] - atas_close[leader.time_ny]
            if leader_market == "ATAS L2":
                expected_lagger_price = leader.price + basis_cfd_minus_atas
            else:
                expected_lagger_price = leader.price - basis_cfd_minus_atas
            prior_or_current = equivalent_pivots(
                lagger_pivots,
                leader,
                first_time=leader.time_ny - timedelta(minutes=maximum_delay),
                last_time=detection_time,
                expected_price=expected_lagger_price,
                known_by=detection_time,
            )
            if prior_or_current:
                continue
            later = equivalent_pivots(
                lagger_pivots,
                leader,
                first_time=detection_time + timedelta(minutes=1),
                last_time=leader.time_ny + timedelta(minutes=maximum_delay),
                expected_price=expected_lagger_price,
            )
            response = min(later, key=lambda item: item.time_ny) if later else None
            delay = (
                int((response.time_ny - leader.time_ny).total_seconds() // 60)
                if response else None
            )
            events.append(
                Event(
                    session_date_ny=leader.time_ny.date().isoformat(),
                    leader=leader_market,
                    lagger=lagger_market,
                    pivot_kind=leader.kind,
                    leader_time_ny=leader.time_ny.isoformat(),
                    detection_time_ny=detection_time.isoformat(),
                    lagger_time_ny=response.time_ny.isoformat() if response else "",
                    delay_minutes=delay,
                    lagger_confirmed_within_window=response is not None,
                    leader_price=leader.price,
                    lagger_price=response.price if response else 0.0,
                    leader_swing_atr=round(leader.swing_atr, 4),
                    lagger_swing_atr=round(response.swing_atr, 4) if response else 0.0,
                    leader_reaction_atr=round(leader.reaction_atr, 4),
                    lagger_reaction_atr=round(response.reaction_atr, 4) if response else 0.0,
                    occurrence_hour_ny=detection_time.hour,
                )
            )

    unique: dict[tuple[str, str, str, str], Event] = {}
    for event in events:
        key = (event.leader, event.pivot_kind, event.leader_time_ny, event.detection_time_ny)
        if key not in unique:
            unique[key] = event
    return sorted(unique.values(), key=lambda item: item.detection_time_ny)


def write_csv(path: Path, rows: list[Event]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(Event.__dataclass_fields__)
    with path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def summarize(events: list[Event], sessions: dict[str, list[Bar]], common_minutes: int) -> dict[str, object]:
    leaders = Counter(item.leader for item in events)
    pivot_kinds = Counter(item.pivot_kind for item in events)
    hours = Counter(item.occurrence_hour_ny for item in events)
    per_session = Counter(item.session_date_ny for item in events)
    delays = [item.delay_minutes for item in events if item.delay_minutes is not None]
    responses = sum(item.lagger_confirmed_within_window for item in events)
    confirmed = [item for item in events if item.lagger_confirmed_within_window]
    confirmed_leaders = Counter(item.leader for item in confirmed)
    confirmed_hours = Counter(item.occurrence_hour_ny for item in confirmed)
    confirmed_cfd_hours = Counter(
        item.occurrence_hour_ny for item in confirmed if item.leader == "CFD MT5"
    )
    confirmed_atas_hours = Counter(
        item.occurrence_hour_ny for item in confirmed if item.leader == "ATAS L2"
    )
    session_count = len(sessions)
    return {
        "rule": "LIDER_ESTRUCTURAL_PIVOTE_ATR_2X2_DST_V3",
        "dst_only": True,
        "minimum_delay_m1": 3,
        "maximum_delay_m1": 8,
        "pivot_confirmation_right_bars": 2,
        "pivot_swing_lookback_m1": 20,
        "minimum_leader_swing_atr": 5.0,
        "minimum_leader_reaction_atr": 1.5,
        "sessions_observed": session_count,
        "common_minutes_observed": common_minutes,
        "events": len(events),
        "confirmed_events": len(confirmed),
        "lagger_confirmed_within_8m": responses,
        "lagger_not_confirmed_within_8m": len(events) - responses,
        "events_per_session": round(len(events) / session_count, 4) if session_count else 0,
        "confirmed_events_per_session": round(len(confirmed) / session_count, 4) if session_count else 0,
        "events_per_60_observed_minutes": round(len(events) * 60 / common_minutes, 4) if common_minutes else 0,
        "estimated_events_per_21_sessions": round(len(events) * 21 / session_count, 2) if session_count else 0,
        "estimated_confirmed_events_per_21_sessions": (
            round(len(confirmed) * 21 / session_count, 2) if session_count else 0
        ),
        "leaders": dict(sorted(leaders.items())),
        "confirmed_leaders": dict(sorted(confirmed_leaders.items())),
        "pivot_kinds": dict(sorted(pivot_kinds.items())),
        "response_delay_mean_m1": round(statistics.fmean(delays), 3) if delays else 0,
        "response_delay_median_m1": statistics.median(delays) if delays else 0,
        "events_by_hour_ny": {f"{hour:02d}:00": count for hour, count in sorted(hours.items())},
        "confirmed_events_by_hour_ny": {
            f"{hour:02d}:00": count for hour, count in sorted(confirmed_hours.items())
        },
        "confirmed_cfd_leads_by_hour_ny": {
            f"{hour:02d}:00": count for hour, count in sorted(confirmed_cfd_hours.items())
        },
        "confirmed_atas_leads_by_hour_ny": {
            f"{hour:02d}:00": count for hour, count in sorted(confirmed_atas_hours.items())
        },
        "events_by_session": dict(sorted(per_session.items())),
        "dates_observed": sorted(sessions),
    }


def markdown(summary: dict[str, object]) -> str:
    leaders = summary["leaders"]
    hours = summary["events_by_hour_ny"]
    confirmed_hours = summary["confirmed_events_by_hour_ny"]
    confirmed_cfd_hours = summary["confirmed_cfd_leads_by_hour_ny"]
    return "\n".join(
        [
            "# Backtest pivotes ATAS L2 vs CFD — DST",
            "",
            f"Regla: `{summary['rule']}`.",
            f"Sesiones observadas: {summary['sessions_observed']}.",
            f"Minutos M1 comunes: {summary['common_minutes_observed']}.",
            f"Eventos: {summary['events']} ({summary['events_per_session']} por sesión).",
            f"Liderazgos confirmados: {summary['confirmed_events']} ({summary['confirmed_events_per_session']} por sesión).",
            f"Proyección confirmada a 21 sesiones: {summary['estimated_confirmed_events_per_21_sessions']}.",
            f"Respuesta posterior en ≤8m: {summary['lagger_confirmed_within_8m']}; sin respuesta: {summary['lagger_not_confirmed_within_8m']}.",
            f"Retraso de las respuestas, medio/mediano: {summary['response_delay_mean_m1']} / {summary['response_delay_median_m1']} velas M1.",
            f"Líderes: {json.dumps(leaders, ensure_ascii=False, sort_keys=True)}.",
            f"Horas NY: {json.dumps(hours, ensure_ascii=False, sort_keys=True)}.",
            f"Horas NY confirmadas: {json.dumps(confirmed_hours, ensure_ascii=False, sort_keys=True)}.",
            f"CFD líder por hora NY: {json.dumps(confirmed_cfd_hours, ensure_ascii=False, sort_keys=True)}.",
            "",
            "La proyección mensual se etiqueta como estimación mientras no estén exportadas todas las sesiones ATAS del mes.",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atas-root", type=Path)
    parser.add_argument("--atas-cache", type=Path)
    parser.add_argument("--terminal", type=Path, required=True)
    parser.add_argument("--symbol", default="USTEC")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--session-start", default="09:30")
    parser.add_argument("--session-end", default="16:00")
    parser.add_argument(
        "--broker-calendar",
        default="us",
        help='Broker clock: "us" (UTC+2/+3 switching with New York) or an IANA zone.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.atas_root and not args.atas_cache:
        raise SystemExit("Indica --atas-root, --atas-cache o ambos")
    start = datetime.fromisoformat(args.start).replace(tzinfo=NY)
    end = datetime.fromisoformat(args.end).replace(tzinfo=NY)
    sessions = load_atas_bars(args.atas_root, args.atas_cache, start, end)
    mt5_bars = load_mt5_bars(
        args.terminal,
        args.symbol,
        start,
        end,
        broker_calendar=args.broker_calendar,
    )
    alignment = diagnose_alignment(sessions, mt5_bars)
    per_session = diagnose_alignment_by_session(sessions, mt5_bars)
    print(json.dumps(
        {"alignment": alignment, "alignment_by_session": per_session},
        indent=2, ensure_ascii=False,
    ))
    if not per_session["all_sessions_aligned"]:
        raise SystemExit(
            f"ABORTADO: {per_session['sessions_misaligned']} sesiones no alinean en shift 0. "
            f"Distribucion: {per_session['best_shift_distribution']}. "
            "Corrige --broker-calendar antes de interpretar nada."
        )
    session_start = datetime.strptime(args.session_start, "%H:%M").time()
    session_end = datetime.strptime(args.session_end, "%H:%M").time()
    all_events: list[Event] = []
    common_minutes = 0
    observed_sessions: dict[str, list[Bar]] = {}
    for day, atas_bars in sorted(sessions.items()):
        common_times = {
            item.time_ny for item in atas_bars
            if session_start <= item.time_ny.time() <= session_end
        }.intersection(mt5_bars)
        common_minutes += len(common_times)
        if len(common_times) < 100:
            continue
        observed_sessions[day] = atas_bars
        atas_common = [item for item in atas_bars if item.time_ny in common_times]
        cfd_common = [mt5_bars[item.time_ny] for item in atas_common]
        atas_pivots = detect_pivots(
            atas_common,
            "ATAS L2",
            minimum_swing_atr=0.50,
            minimum_reaction_atr=0.25,
            swing_lookback=20,
        )
        cfd_pivots = detect_pivots(
            cfd_common,
            "CFD MT5",
            minimum_swing_atr=0.50,
            minimum_reaction_atr=0.25,
            swing_lookback=20,
        )
        all_events.extend(
            detect_lead_events(
                atas_pivots,
                cfd_pivots,
                atas_common,
                cfd_common,
                common_times,
                minimum_swing_atr=5.0,
                minimum_reaction_atr=1.5,
            )
        )

    summary = summarize(all_events, observed_sessions, common_minutes)
    summary["mapping"] = "additive_basis_frozen_at_pivot_minute"
    summary["broker_calendar"] = args.broker_calendar
    summary["alignment"] = alignment
    summary["alignment_by_session"] = per_session
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "atas_mt5_pivot_events.csv", all_events)
    (args.output / "atas_mt5_pivot_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    (args.output / "atas_mt5_pivot_summary.md").write_text(markdown(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
