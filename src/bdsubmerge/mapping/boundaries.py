"""Candidate timeline boundary construction and normalization."""

from __future__ import annotations

from collections.abc import Iterable

from .models import BoundarySource, MediaTick90k, TimelineBoundary


def merge_boundaries(
    boundaries: Iterable[TimelineBoundary], *, tolerance_90k: MediaTick90k = MediaTick90k(0)
) -> tuple[TimelineBoundary, ...]:
    """Merge nearby boundaries while retaining every source reference.

    The earliest time wins, making the result independent of input ordering. User-created
    boundaries are never silently discarded; their flag and notes are retained.
    """

    tolerance = int(tolerance_90k)
    if tolerance < 0:
        raise ValueError("boundary merge tolerance cannot be negative")
    ordered = sorted(boundaries, key=lambda item: (int(item.time_90k), item.id))
    groups: list[list[TimelineBoundary]] = []
    for boundary in ordered:
        if groups and int(boundary.time_90k) - int(groups[-1][0].time_90k) <= tolerance:
            groups[-1].append(boundary)
        else:
            groups.append([boundary])

    merged: list[TimelineBoundary] = []
    for group in groups:
        first = group[0]
        sources = tuple(sorted({source for item in group for source in item.sources}))
        notes = tuple(dict.fromkeys(item.note for item in group if item.note))
        merged.append(
            TimelineBoundary(
                id=first.id,
                time_90k=first.time_90k,
                sources=sources,
                confidence=max(item.confidence for item in group),
                enabled=any(item.enabled for item in group),
                user_created=any(item.user_created for item in group),
                note="; ".join(notes),
            )
        )
    return tuple(merged)


def boundary(
    boundary_id: str,
    time_90k: int,
    *sources: BoundarySource,
    confidence: int = 100,
    enabled: bool = True,
    user_created: bool = False,
    note: str = "",
) -> TimelineBoundary:
    """Small adapter-friendly constructor for integer parser output."""

    return TimelineBoundary(
        id=boundary_id,
        time_90k=MediaTick90k(time_90k),
        sources=tuple(sources),
        confidence=confidence,
        enabled=enabled,
        user_created=user_created,
        note=note,
    )
