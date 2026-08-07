#!/usr/bin/env python3
"""Strict streaming decoder for ATAS Cache_v2 trade/depth block files.

The decoder is intentionally read-only.  It implements the on-disk structure
used by OFT.Core.Storage.DataStorage.FileDataStorage in Blocks mode:

    int32 magic ("ATAS")
    int32 context_length
    context SBE message
    repeated { int32 block_length, block SBE messages }

Only the NQ continuous-future messages required by this research are accepted.
An unknown template or malformed block is a hard error so corrupt/misaligned
bytes cannot silently become market data.
"""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO, Iterator

import numpy as np


ATAS_MAGIC = 1_396_790_337
DOTNET_EPOCH = datetime(1, 1, 1, tzinfo=timezone.utc)

TEMPLATE_SECURITY_METADATA = 90
TEMPLATE_TRADE_CONTEXT = 92
TEMPLATE_DEPTH_CONTEXT = 93
TEMPLATE_FUT_TRADE = 101
TEMPLATE_MARKET_DEPTH = 130

CONTEXT_SIZES = {
    TEMPLATE_TRADE_CONTEXT: 32,
    TEMPLATE_DEPTH_CONTEXT: 24,
}

CACHE_RECORD_DTYPE = np.dtype(
    [
        ("template_id", "u1"),
        ("ticks", "<i8"),
        ("side_code", "u1"),
        ("price_raw", "<i4"),
        ("volume_raw", "<u4"),
    ],
    align=False,
)


@dataclass(frozen=True)
class CacheContext:
    template_id: int
    tick_size: float
    lot_size: float
    last_ticks: int
    last_id: int | None


@dataclass(frozen=True)
class CacheEvent:
    template_id: int
    ticks: int
    timestamp_utc: datetime
    side_code: int
    side: str
    price_raw: int
    price: float
    volume_raw: int
    volume: float
    block_index: int
    message_index: int


def dotnet_ticks_to_datetime(ticks: int) -> datetime:
    if ticks < 0 or ticks > 3_155_378_975_999_999_999:
        raise ValueError(f".NET ticks outside DateTime range: {ticks}")
    seconds, remainder = divmod(ticks, 10_000_000)
    microseconds = remainder // 10
    return DOTNET_EPOCH + timedelta(seconds=seconds, microseconds=microseconds)


def _read_exact(stream: BinaryIO, size: int, label: str) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise ValueError(
            f"Truncated {label}: expected {size} bytes, observed {len(data)}"
        )
    return data


def read_context(stream: BinaryIO) -> CacheContext:
    magic, context_length = struct.unpack("<ii", _read_exact(stream, 8, "file header"))
    if magic != ATAS_MAGIC:
        raise ValueError(f"Invalid ATAS magic: {magic} (0x{magic & 0xFFFFFFFF:08X})")
    if context_length <= 0 or context_length > 1_024:
        raise ValueError(f"Implausible context length: {context_length}")

    payload = _read_exact(stream, context_length, "context")
    template_id = payload[0]
    expected_body = CONTEXT_SIZES.get(template_id)
    if expected_body is None:
        raise ValueError(f"Unsupported context template: {template_id}")
    if context_length != 1 + expected_body:
        raise ValueError(
            f"Context size mismatch for template {template_id}: "
            f"expected {1 + expected_body}, observed {context_length}"
        )

    tick_size, lot_size, last_ticks = struct.unpack_from("<ddq", payload, 1)
    last_id = struct.unpack_from("<q", payload, 25)[0] if template_id == 92 else None
    if tick_size <= 0 or lot_size <= 0:
        raise ValueError(
            f"Invalid context scale: tick_size={tick_size}, lot_size={lot_size}"
        )
    return CacheContext(template_id, tick_size, lot_size, last_ticks, last_id)


def iter_cache_events(
    path: Path,
    *,
    start_utc: datetime | None = None,
    end_utc: datetime | None = None,
) -> Iterator[CacheEvent]:
    """Yield decoded events in file order for [start_utc, end_utc)."""

    with path.open("rb") as stream:
        context = read_context(stream)
        tick_size = context.tick_size
        lot_size = context.lot_size
        block_index = 0
        message_index = 0

        while True:
            length_bytes = stream.read(4)
            if not length_bytes:
                break
            if len(length_bytes) != 4:
                raise ValueError(
                    f"Truncated block-length prefix at block {block_index}"
                )
            block_length = struct.unpack("<i", length_bytes)[0]
            if block_length == 0:
                block_index += 1
                continue
            if block_length < 0 or block_length > 256 * 1024 * 1024:
                raise ValueError(
                    f"Implausible block length {block_length} at block {block_index}"
                )
            payload = _read_exact(stream, block_length, f"block {block_index}")
            offset = 0

            while offset < block_length:
                template_id = payload[offset]
                offset += 1

                if template_id == 0:
                    if offset >= block_length:
                        raise ValueError(
                            f"Truncated padding message at block {block_index}"
                        )
                    offset += 1
                    continue

                if template_id == TEMPLATE_SECURITY_METADATA:
                    if offset + 16 > block_length:
                        raise ValueError(
                            f"Truncated metadata at block {block_index}, offset {offset - 1}"
                        )
                    tick_size, lot_size = struct.unpack_from("<dd", payload, offset)
                    offset += 16
                    if tick_size <= 0 or lot_size <= 0:
                        raise ValueError(
                            f"Invalid metadata scale at block {block_index}: "
                            f"tick={tick_size}, lot={lot_size}"
                        )
                    continue

                if template_id not in (TEMPLATE_FUT_TRADE, TEMPLATE_MARKET_DEPTH):
                    raise ValueError(
                        f"Unsupported template {template_id} at block "
                        f"{block_index}, offset {offset - 1}"
                    )
                if offset + 17 > block_length:
                    raise ValueError(
                        f"Truncated market message at block {block_index}, "
                        f"offset {offset - 1}"
                    )

                ticks, side_code, price_raw, volume_raw = struct.unpack_from(
                    "<qBiI", payload, offset
                )
                offset += 17
                timestamp_utc = dotnet_ticks_to_datetime(ticks)

                if template_id == TEMPLATE_FUT_TRADE:
                    side = {0: "NONE", 1: "BUY", 2: "SELL"}.get(side_code)
                else:
                    side = {0: "BID", 1: "ASK"}.get(side_code)
                if side is None:
                    raise ValueError(
                        f"Invalid side {side_code} for template {template_id} "
                        f"at block {block_index}"
                    )

                if start_utc is not None and timestamp_utc < start_utc:
                    message_index += 1
                    continue
                if end_utc is not None and timestamp_utc >= end_utc:
                    return

                yield CacheEvent(
                    template_id=template_id,
                    ticks=ticks,
                    timestamp_utc=timestamp_utc,
                    side_code=side_code,
                    side=side,
                    price_raw=price_raw,
                    price=price_raw * tick_size,
                    volume_raw=volume_raw,
                    volume=volume_raw * lot_size,
                    block_index=block_index,
                    message_index=message_index,
                )
                message_index += 1

            if offset != block_length:
                raise ValueError(
                    f"Block {block_index} not consumed exactly: "
                    f"{offset}/{block_length}"
                )
            block_index += 1


def load_cache_window(
    path: Path,
    *,
    start_ticks: int,
    end_ticks: int,
) -> tuple[CacheContext, np.ndarray]:
    """Load a tick interval with vectorized, strict block decoding.

    This still validates every SBE record in every block, but NumPy performs the
    fixed-record scan without allocating Python objects for out-of-window rows.
    The source file is never modified or copied.
    """

    if end_ticks <= start_ticks:
        raise ValueError("end_ticks must be greater than start_ticks")

    chunks: list[np.ndarray] = []
    expected_template: int | None = None
    with path.open("rb") as stream:
        context = read_context(stream)
        if context.template_id == TEMPLATE_TRADE_CONTEXT:
            expected_template = TEMPLATE_FUT_TRADE
        elif context.template_id == TEMPLATE_DEPTH_CONTEXT:
            expected_template = TEMPLATE_MARKET_DEPTH

        block_index = 0
        while True:
            length_bytes = stream.read(4)
            if not length_bytes:
                break
            if len(length_bytes) != 4:
                raise ValueError(
                    f"Truncated block-length prefix at block {block_index}"
                )
            block_length = struct.unpack("<i", length_bytes)[0]
            if block_length == 0:
                block_index += 1
                continue
            if block_length < 0 or block_length > 256 * 1024 * 1024:
                raise ValueError(
                    f"Implausible block length {block_length} at block {block_index}"
                )

            payload = _read_exact(stream, block_length, f"block {block_index}")
            offset = 0
            while offset < block_length and payload[offset] in (
                0,
                TEMPLATE_SECURITY_METADATA,
            ):
                template_id = payload[offset]
                if template_id == 0:
                    if offset + 2 > block_length:
                        raise ValueError(
                            f"Truncated padding at block {block_index}"
                        )
                    offset += 2
                    continue

                if offset + 17 > block_length:
                    raise ValueError(
                        f"Truncated metadata at block {block_index}"
                    )
                tick_size, lot_size = struct.unpack_from("<dd", payload, offset + 1)
                if (
                    not np.isclose(tick_size, context.tick_size)
                    or not np.isclose(lot_size, context.lot_size)
                ):
                    raise ValueError(
                        f"Scale change inside block {block_index}: "
                        f"{tick_size}/{lot_size}"
                    )
                offset += 17

            remaining = block_length - offset
            if remaining % CACHE_RECORD_DTYPE.itemsize != 0:
                raise ValueError(
                    f"Block {block_index} is not fixed-record aligned after "
                    f"metadata: remaining={remaining}"
                )
            records = np.frombuffer(
                payload,
                dtype=CACHE_RECORD_DTYPE,
                count=remaining // CACHE_RECORD_DTYPE.itemsize,
                offset=offset,
            )
            if records.size:
                if expected_template is None or np.any(
                    records["template_id"] != expected_template
                ):
                    observed = np.unique(records["template_id"]).tolist()
                    raise ValueError(
                        f"Unexpected templates in block {block_index}: {observed}"
                    )
                valid_sides = (records["side_code"] <= 2) if expected_template == 101 else (
                    records["side_code"] <= 1
                )
                if not np.all(valid_sides):
                    observed = np.unique(records["side_code"][~valid_sides]).tolist()
                    raise ValueError(
                        f"Invalid side codes in block {block_index}: {observed}"
                    )
                mask = (records["ticks"] >= start_ticks) & (
                    records["ticks"] < end_ticks
                )
                if np.any(mask):
                    chunks.append(records[mask].copy())
            block_index += 1

    if not chunks:
        return context, np.empty(0, dtype=CACHE_RECORD_DTYPE)
    return context, np.concatenate(chunks)


def summarize(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        context = read_context(stream)

    count = 0
    first: CacheEvent | None = None
    last: CacheEvent | None = None
    sides: Counter[str] = Counter()
    templates: Counter[int] = Counter()
    max_block = -1
    for event in iter_cache_events(path):
        if first is None:
            first = event
        last = event
        count += 1
        sides[event.side] += 1
        templates[event.template_id] += 1
        max_block = max(max_block, event.block_index)

    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "context": {
            **asdict(context),
            "last_time_utc": dotnet_ticks_to_datetime(context.last_ticks).isoformat(),
        },
        "events": count,
        "blocks_observed": max_block + 1,
        "templates": dict(sorted(templates.items())),
        "sides": dict(sorted(sides.items())),
        "first": asdict(first) if first else None,
        "last": asdict(last) if last else None,
    }


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Not JSON serializable: {type(value)!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Decode the entire file and print an integrity summary.",
    )
    parser.add_argument(
        "--head",
        type=int,
        default=0,
        help="Print the first N decoded events as JSON lines.",
    )
    args = parser.parse_args()

    if not args.path.is_file():
        parser.error(f"File not found: {args.path}")

    if args.summary:
        print(json.dumps(summarize(args.path), indent=2, default=_json_default))
        return 0

    limit = args.head if args.head > 0 else 10
    for index, event in enumerate(iter_cache_events(args.path)):
        print(json.dumps(asdict(event), default=_json_default))
        if index + 1 >= limit:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
