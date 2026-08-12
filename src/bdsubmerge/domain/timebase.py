"""Exact conversions for the project's integer 90 kHz media clock."""

from __future__ import annotations

from enum import StrEnum
from typing import NewType

MediaTick90k = NewType("MediaTick90k", int)

TICKS_PER_SECOND = 90_000
TICKS_PER_MILLISECOND = 90
TICKS_PER_CENTISECOND = 900


class RoundingMode(StrEnum):
    """Explicit integer rounding policy for a target time unit."""

    FLOOR = "floor"
    CEIL = "ceil"


def from_45k(value: int) -> MediaTick90k:
    """Convert an MPLS 45 kHz timestamp without loss."""
    return MediaTick90k(value * 2)


def from_milliseconds(value: int) -> MediaTick90k:
    """Convert an integer millisecond timestamp without loss."""
    return MediaTick90k(value * TICKS_PER_MILLISECOND)


def from_centiseconds(value: int) -> MediaTick90k:
    """Convert an integer centisecond timestamp without loss."""
    return MediaTick90k(value * TICKS_PER_CENTISECOND)


def add(left: MediaTick90k, right: MediaTick90k) -> MediaTick90k:
    """Add media times while retaining the distinct return type."""
    return MediaTick90k(left + right)


def subtract(left: MediaTick90k, right: MediaTick90k) -> MediaTick90k:
    """Subtract media times while retaining the distinct return type."""
    return MediaTick90k(left - right)


def quantize(value: MediaTick90k, quantum: int, mode: RoundingMode) -> int:
    """Return an integer target-unit count using the requested direction."""
    if quantum <= 0:
        raise ValueError("quantum must be positive")
    if mode is RoundingMode.FLOOR:
        return value // quantum
    return -(-value // quantum)


def to_milliseconds(value: MediaTick90k, mode: RoundingMode) -> int:
    return quantize(value, TICKS_PER_MILLISECOND, mode)


def to_centiseconds(value: MediaTick90k, mode: RoundingMode) -> int:
    return quantize(value, TICKS_PER_CENTISECOND, mode)


def serialized_interval(
    start: MediaTick90k,
    end: MediaTick90k,
    *,
    quantum: int,
) -> tuple[int, int]:
    """Round an interval outwards and guarantee a positive serialized span."""
    start_units = quantize(start, quantum, RoundingMode.FLOOR)
    end_units = quantize(end, quantum, RoundingMode.CEIL)
    if end_units <= start_units:
        end_units = start_units + 1
    return start_units, end_units
