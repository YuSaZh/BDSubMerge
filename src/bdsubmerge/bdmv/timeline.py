"""Pure MPLS timeline construction and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bdsubmerge.domain.models import (
    PgStreamInfo,
    PlaylistInfo,
    PlaylistMarkInfo,
    PlayItemInfo,
    ReferenceStatus,
)
from bdsubmerge.domain.timebase import MediaTick90k, from_45k


@dataclass(frozen=True, slots=True)
class RawPlayItem:
    clip_id: str
    codec_id: str
    in_time_45k: int
    out_time_45k: int
    connection_condition: int = 0
    is_multi_angle: bool = False
    selected_angle: int = 0
    angle_count: int = 1
    primary_pg_streams: tuple[PgStreamInfo, ...] = ()


@dataclass(frozen=True, slots=True)
class RawPlaylistMark:
    mark_type: int
    play_item_index: int
    timestamp_45k: int
    entry_es_pid: int | None = None
    duration_45k: int | None = None


def _reference_status(layout_stream: Path, layout_clipinf: Path, clip_id: str) -> ReferenceStatus:
    return ReferenceStatus(
        m2ts_exists=(layout_stream / f"{clip_id}.m2ts").is_file(),
        clpi_exists=(layout_clipinf / f"{clip_id}.clpi").is_file(),
    )


def build_playlist(
    path: Path,
    raw_items: tuple[RawPlayItem, ...],
    raw_marks: tuple[RawPlaylistMark, ...],
    *,
    stream_path: Path,
    clipinf_path: Path,
) -> PlaylistInfo:
    """Build an immutable logical timeline from parser-neutral MPLS fields."""
    warnings: list[str] = []
    errors: list[str] = []
    play_items: list[PlayItemInfo] = []
    logical_start = MediaTick90k(0)

    for index, raw in enumerate(raw_items):
        if raw.out_time_45k <= raw.in_time_45k:
            errors.append(f"PlayItem {index} OUT time must be greater than IN time")
            duration = MediaTick90k(0)
        else:
            duration = from_45k(raw.out_time_45k - raw.in_time_45k)
        references = _reference_status(stream_path, clipinf_path, raw.clip_id)
        if not references.m2ts_exists:
            warnings.append(f"PlayItem {index} missing STREAM/{raw.clip_id}.m2ts")
        if not references.clpi_exists:
            warnings.append(f"PlayItem {index} missing CLIPINF/{raw.clip_id}.clpi")
        if raw.is_multi_angle:
            warnings.append(
                f"PlayItem {index} is multi-angle; explicitly selected angle {raw.selected_angle}"
            )
        logical_end = MediaTick90k(logical_start + duration)
        play_items.append(
            PlayItemInfo(
                index=index,
                clip_id=raw.clip_id,
                codec_id=raw.codec_id,
                in_time_45k=raw.in_time_45k,
                out_time_45k=raw.out_time_45k,
                logical_start_90k=logical_start,
                logical_end_90k=logical_end,
                connection_condition=raw.connection_condition,
                is_multi_angle=raw.is_multi_angle,
                selected_angle=raw.selected_angle,
                angle_count=max(raw.angle_count, 1),
                references=references,
                primary_pg_streams=raw.primary_pg_streams,
            )
        )
        logical_start = logical_end

    marks: list[PlaylistMarkInfo] = []
    previous_valid_time: MediaTick90k | None = None
    seen_times: set[MediaTick90k] = set()
    for index, raw in enumerate(raw_marks):
        absolute: MediaTick90k | None = None
        if not 0 <= raw.play_item_index < len(play_items):
            errors.append(
                f"Playlist mark {index} references missing PlayItem {raw.play_item_index}"
            )
        else:
            item = play_items[raw.play_item_index]
            if raw.timestamp_45k < item.in_time_45k:
                errors.append(f"Playlist mark {index} is before PlayItem IN time")
            elif raw.timestamp_45k > item.out_time_45k:
                errors.append(f"Playlist mark {index} is after PlayItem OUT time")
            else:
                absolute = MediaTick90k(
                    item.logical_start_90k + from_45k(raw.timestamp_45k - item.in_time_45k)
                )
                if absolute in seen_times:
                    warnings.append(f"Playlist mark {index} duplicates an earlier chapter time")
                if previous_valid_time is not None and absolute < previous_valid_time:
                    warnings.append(f"Playlist mark {index} is out of chronological order")
                seen_times.add(absolute)
                previous_valid_time = absolute
        marks.append(
            PlaylistMarkInfo(
                index=index,
                mark_type=raw.mark_type,
                play_item_index=raw.play_item_index,
                timestamp_45k=raw.timestamp_45k,
                time_90k=absolute,
                entry_es_pid=raw.entry_es_pid,
                duration_45k=raw.duration_45k,
            )
        )

    if not play_items or logical_start == 0:
        errors.append("Playlist total duration is zero")
    fingerprint = tuple(
        (item.clip_id, item.in_time_45k, item.out_time_45k, item.selected_angle)
        for item in play_items
    )
    return PlaylistInfo(
        path=path,
        stem=path.stem,
        duration_90k=logical_start,
        play_items=tuple(play_items),
        marks=tuple(marks),
        warnings=tuple(warnings),
        errors=tuple(errors),
        timeline_fingerprint=fingerprint,
    )
