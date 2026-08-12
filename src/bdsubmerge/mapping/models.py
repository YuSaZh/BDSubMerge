"""Project-owned models for deterministic episode-to-timeline mapping."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from bdsubmerge.domain.timebase import MediaTick90k


class BoundaryKind(StrEnum):
    PLAYLIST_START = "playlist_start"
    PLAYLIST_END = "playlist_end"
    PLAY_ITEM_START = "play_item_start"
    PLAY_ITEM_END = "play_item_end"
    CHAPTER = "chapter"
    USER = "user"


class MappingConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True, order=True)
class BoundarySource:
    """One reason a candidate boundary exists."""

    kind: BoundaryKind
    reference: str = ""


@dataclass(frozen=True, slots=True)
class TimelineBoundary:
    id: str
    time_90k: MediaTick90k
    sources: tuple[BoundarySource, ...]
    confidence: int = 100
    enabled: bool = True
    user_created: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("boundary id cannot be empty")
        if int(self.time_90k) < 0:
            raise ValueError("boundary time cannot be negative")
        if not self.sources:
            raise ValueError("boundary must retain at least one source")
        if not 0 <= self.confidence <= 100:
            raise ValueError("boundary confidence must be between 0 and 100")

    @property
    def kinds(self) -> frozenset[BoundaryKind]:
        return frozenset(source.kind for source in self.sources)


@dataclass(frozen=True, slots=True)
class EpisodeRequest:
    """Minimal mapping input, deliberately independent of subtitle adapters."""

    id: str
    effective_end_90k: MediaTick90k
    subtitle_ref: str = ""
    duration_estimated: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("episode id cannot be empty")
        if int(self.effective_end_90k) <= 0:
            raise ValueError("effective subtitle duration must be positive")


@dataclass(frozen=True, slots=True)
class MappingLock:
    episode_id: str
    start_boundary_id: str
    end_boundary_id: str
    manual_offset_90k: MediaTick90k = field(default_factory=lambda: MediaTick90k(0))


@dataclass(frozen=True, slots=True)
class EpisodeMapping:
    episode_id: str
    subtitle_ref: str
    start_boundary: TimelineBoundary
    end_boundary: TimelineBoundary
    manual_offset_90k: MediaTick90k
    score: int
    confidence: MappingConfidence
    locked: bool = False
    warnings: tuple[str, ...] = ()

    @property
    def interval_duration_90k(self) -> MediaTick90k:
        return MediaTick90k(
            int(self.end_boundary.time_90k) - int(self.start_boundary.time_90k)
        )

    @property
    def final_offset_90k(self) -> MediaTick90k:
        return MediaTick90k(int(self.start_boundary.time_90k) + int(self.manual_offset_90k))


@dataclass(frozen=True, slots=True)
class MappingResult:
    mappings: tuple[EpisodeMapping, ...]
    total_cost: int
    confidence: MappingConfidence
    warnings: tuple[str, ...] = ()

    @property
    def has_low_confidence(self) -> bool:
        return any(mapping.confidence is MappingConfidence.LOW for mapping in self.mappings)


@dataclass(frozen=True, slots=True)
class MappingCostConfig:
    """Integer-only weights; all returned costs are deterministic media-tick costs."""

    early_end_weight: int = 1
    overrun_weight: int = 8
    boundary_penalty_per_percent: int = 9_000
    skipped_timeline_weight: int = 1
    skipped_timeline_divisor: int = 50
    short_interval_threshold_90k: MediaTick90k = field(
        default_factory=lambda: MediaTick90k(45 * 90_000)
    )
    short_interval_penalty: int = 180 * 90_000
    estimated_duration_penalty: int = 15 * 90_000
    medium_cost_ratio_percent: int = 8
    low_cost_ratio_percent: int = 18
    ambiguity_margin_percent: int = 3

    def __post_init__(self) -> None:
        integer_fields = (
            self.early_end_weight,
            self.overrun_weight,
            self.boundary_penalty_per_percent,
            self.skipped_timeline_weight,
            self.skipped_timeline_divisor,
            int(self.short_interval_threshold_90k),
            self.short_interval_penalty,
            self.estimated_duration_penalty,
        )
        if any(value < 0 for value in integer_fields) or self.skipped_timeline_divisor == 0:
            raise ValueError("mapping cost weights must be non-negative and divisors positive")
