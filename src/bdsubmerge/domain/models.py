"""Immutable project models shared by the application surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from bdsubmerge.domain.timebase import MediaTick90k


class PlaylistConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ReferenceStatus:
    m2ts_exists: bool
    clpi_exists: bool

    @property
    def complete(self) -> bool:
        return self.m2ts_exists and self.clpi_exists


@dataclass(frozen=True, slots=True)
class BdmvLayout:
    selected_path: Path
    disc_container_path: Path
    bdmv_path: Path
    index_bdmv_path: Path
    playlist_path: Path
    clipinf_path: Path
    stream_path: Path


@dataclass(frozen=True, slots=True)
class PgStreamInfo:
    pid: int | None = None
    language: str | None = None
    coding_type: int | str | None = None


@dataclass(frozen=True, slots=True)
class PlayItemInfo:
    index: int
    clip_id: str
    codec_id: str
    in_time_45k: int
    out_time_45k: int
    logical_start_90k: MediaTick90k
    logical_end_90k: MediaTick90k
    connection_condition: int
    is_multi_angle: bool
    selected_angle: int
    angle_count: int
    references: ReferenceStatus
    primary_pg_streams: tuple[PgStreamInfo, ...] = ()

    @property
    def duration_90k(self) -> MediaTick90k:
        return MediaTick90k(self.logical_end_90k - self.logical_start_90k)


@dataclass(frozen=True, slots=True)
class PlaylistMarkInfo:
    index: int
    mark_type: int
    play_item_index: int
    timestamp_45k: int
    time_90k: MediaTick90k | None
    entry_es_pid: int | None = None
    duration_45k: int | None = None


TimelineFingerprint = tuple[tuple[str, int, int, int], ...]


@dataclass(frozen=True, slots=True)
class PlaylistInfo:
    path: Path
    stem: str
    duration_90k: MediaTick90k
    play_items: tuple[PlayItemInfo, ...]
    marks: tuple[PlaylistMarkInfo, ...]
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    score: int = 0
    confidence: PlaylistConfidence = PlaylistConfidence.LOW
    recommendation_reasons: tuple[str, ...] = ()
    timeline_fingerprint: TimelineFingerprint = ()

    @property
    def is_available(self) -> bool:
        return not self.errors

    @property
    def unique_clip_count(self) -> int:
        return len({item.clip_id for item in self.play_items})

    @property
    def repeated_clip_count(self) -> int:
        return len(self.play_items) - self.unique_clip_count

    @property
    def repeated_clip_ratio_per_mille(self) -> int:
        if not self.play_items:
            return 0
        return self.repeated_clip_count * 1000 // len(self.play_items)

    @property
    def has_multi_angle(self) -> bool:
        return any(item.is_multi_angle for item in self.play_items)

    @property
    def references_complete(self) -> bool:
        return all(item.references.complete for item in self.play_items)
