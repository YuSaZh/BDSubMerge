"""Read-only, Qt-free projections for playlist and source-subtitle details."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from bdsubmerge.domain.models import PlaylistInfo
from bdsubmerge.domain.timebase import TICKS_PER_SECOND
from bdsubmerge.subtitles import AssDocument, PgsDocument, PgsSegmentType
from bdsubmerge.subtitles.ass_document import AssEntry, AssRawLine

from .models import SubtitleAsset


@dataclass(frozen=True, slots=True)
class PlaylistPgStreamDisplay:
    pid: int | None
    language: str | None
    coding_type: int | str | None


@dataclass(frozen=True, slots=True)
class PlaylistPlayItemDisplay:
    index: int
    clip_id: str
    codec_id: str
    in_time_45k: int
    out_time_45k: int
    logical_start_90k: int
    logical_end_90k: int
    duration_90k: int
    connection_condition: int
    is_multi_angle: bool
    selected_angle: int
    angle_count: int
    m2ts_exists: bool
    clpi_exists: bool
    primary_pg_streams: tuple[PlaylistPgStreamDisplay, ...]


@dataclass(frozen=True, slots=True)
class PlaylistMarkDisplay:
    index: int
    mark_type: int
    play_item_index: int
    timestamp_45k: int
    time_90k: int | None
    entry_es_pid: int | None
    duration_45k: int | None


@dataclass(frozen=True, slots=True)
class PlaylistStructureDisplay:
    path: Path
    stem: str
    duration_90k: int
    score: int
    confidence: str
    is_available: bool
    unique_clip_count: int
    repeated_clip_count: int
    repeated_clip_ratio_per_mille: int
    has_multi_angle: bool
    references_complete: bool
    recommendation_reasons: tuple[str, ...]
    play_items: tuple[PlaylistPlayItemDisplay, ...]
    marks: tuple[PlaylistMarkDisplay, ...]
    timeline_fingerprint: tuple[tuple[str, int, int, int], ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SubtitleSectionDisplay:
    name: str
    normalized_name: str
    entry_count: int


@dataclass(frozen=True, slots=True)
class PgsSegmentDisplay:
    segment_type: int
    name: str
    packet_count: int


@dataclass(frozen=True, slots=True)
class SubtitleDetailsDisplay:
    path: Path
    filename: str
    format: str
    encoding: str | None
    bom: bool
    event_count: int
    style_count: int
    earliest_start_90k: int | None
    raw_end_90k: int | None
    effective_end_90k: int | None
    suspected_long_tail: bool
    duration_estimated: bool
    play_res_x: int | None
    play_res_y: int | None
    font_attachment_names: tuple[str, ...]
    graphic_attachment_names: tuple[str, ...]
    has_aegisub_extradata: bool
    aegisub_extradata_entry_count: int
    sections: tuple[SubtitleSectionDisplay, ...]
    pgs_packet_count: int
    pgs_segments: tuple[PgsSegmentDisplay, ...]
    warnings: tuple[str, ...]

    @property
    def has_font_attachments(self) -> bool:
        return bool(self.font_attachment_names)

    @property
    def has_graphic_attachments(self) -> bool:
        return bool(self.graphic_attachment_names)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


def build_playlist_structure(playlist: PlaylistInfo) -> PlaylistStructureDisplay:
    """Project a parsed playlist without retaining adapter or UI objects."""

    play_items = tuple(
        PlaylistPlayItemDisplay(
            index=item.index,
            clip_id=item.clip_id,
            codec_id=item.codec_id,
            in_time_45k=item.in_time_45k,
            out_time_45k=item.out_time_45k,
            logical_start_90k=int(item.logical_start_90k),
            logical_end_90k=int(item.logical_end_90k),
            duration_90k=int(item.duration_90k),
            connection_condition=item.connection_condition,
            is_multi_angle=item.is_multi_angle,
            selected_angle=item.selected_angle,
            angle_count=item.angle_count,
            m2ts_exists=item.references.m2ts_exists,
            clpi_exists=item.references.clpi_exists,
            primary_pg_streams=tuple(
                PlaylistPgStreamDisplay(stream.pid, stream.language, stream.coding_type)
                for stream in item.primary_pg_streams
            ),
        )
        for item in playlist.play_items
    )
    marks = tuple(
        PlaylistMarkDisplay(
            index=mark.index,
            mark_type=mark.mark_type,
            play_item_index=mark.play_item_index,
            timestamp_45k=mark.timestamp_45k,
            time_90k=int(mark.time_90k) if mark.time_90k is not None else None,
            entry_es_pid=mark.entry_es_pid,
            duration_45k=mark.duration_45k,
        )
        for mark in playlist.marks
    )
    return PlaylistStructureDisplay(
        path=playlist.path,
        stem=playlist.stem,
        duration_90k=int(playlist.duration_90k),
        score=playlist.score,
        confidence=playlist.confidence.value,
        is_available=playlist.is_available,
        unique_clip_count=playlist.unique_clip_count,
        repeated_clip_count=playlist.repeated_clip_count,
        repeated_clip_ratio_per_mille=playlist.repeated_clip_ratio_per_mille,
        has_multi_angle=playlist.has_multi_angle,
        references_complete=playlist.references_complete,
        recommendation_reasons=playlist.recommendation_reasons,
        play_items=play_items,
        marks=marks,
        timeline_fingerprint=playlist.timeline_fingerprint,
        warnings=playlist.warnings,
        errors=playlist.errors,
    )


def build_subtitle_details(
    asset: SubtitleAsset,
    *,
    warnings: tuple[str, ...] = (),
) -> SubtitleDetailsDisplay:
    """Project one loaded subtitle into immutable source-detail data."""

    document = asset.document
    font_names: tuple[str, ...] = ()
    graphic_names: tuple[str, ...] = ()
    has_extradata = False
    extradata_count = 0
    sections: tuple[SubtitleSectionDisplay, ...] = ()
    packet_count = 0
    segments: tuple[PgsSegmentDisplay, ...] = ()
    document_warnings: tuple[str, ...] = ()

    if isinstance(document, AssDocument):
        font_names = _attachment_names(document, "Fonts", "fontname")
        graphic_names = _attachment_names(document, "Graphics", "filename")
        extradata = document.section("Aegisub Extradata")
        extradata_count = len(extradata.entries) if extradata is not None else 0
        has_extradata = extradata is not None
        sections = tuple(
            SubtitleSectionDisplay(section.name, section.normalized_name, len(section.entries))
            for section in document.sections
        )
    elif isinstance(document, PgsDocument):
        packet_count = len(document.packets)
        segments = _pgs_segment_summary(document)
        document_warnings = document.warnings

    analysis = asset.analysis
    combined_warnings = tuple(dict.fromkeys((*warnings, *document_warnings)))
    return SubtitleDetailsDisplay(
        path=asset.path,
        filename=asset.path.name,
        format=asset.format.value,
        encoding=asset.encoding,
        bom=asset.bom,
        event_count=analysis.event_count,
        style_count=analysis.style_count,
        earliest_start_90k=analysis.earliest_start_ticks,
        raw_end_90k=analysis.raw_end_ticks,
        effective_end_90k=analysis.effective_end_ticks,
        suspected_long_tail=analysis.suspected_long_tail,
        duration_estimated=analysis.duration_estimated,
        play_res_x=analysis.play_res_x,
        play_res_y=analysis.play_res_y,
        font_attachment_names=font_names,
        graphic_attachment_names=graphic_names,
        has_aegisub_extradata=has_extradata,
        aegisub_extradata_entry_count=extradata_count,
        sections=sections,
        pgs_packet_count=packet_count,
        pgs_segments=segments,
        warnings=combined_warnings,
    )


def format_ticks_90k(value: int | None) -> str:
    """Render a tick value without using floating-point seconds."""

    if value is None:
        return "unknown"
    sign = "-" if value < 0 else ""
    absolute_ticks = abs(value)
    total_milliseconds = absolute_ticks * 1_000 // TICKS_PER_SECOND
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    clock = f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    return f"{clock} ({value} ticks)"


def format_playlist_structure(details: PlaylistStructureDisplay) -> str:
    """Format complete parsed playlist information for display or text export."""

    lines = [
        f"Playlist: {details.stem}",
        f"Path: {details.path}",
        f"Duration: {format_ticks_90k(details.duration_90k)}",
        f"Available: {_yes_no(details.is_available)}",
        f"Score: {details.score}",
        f"Confidence: {details.confidence}",
        f"Unique clips: {details.unique_clip_count}",
        f"Repeated clips: {details.repeated_clip_count}",
        f"Repeated clip ratio (per mille): {details.repeated_clip_ratio_per_mille}",
        f"Multi-angle: {_yes_no(details.has_multi_angle)}",
        f"References complete: {_yes_no(details.references_complete)}",
        "Recommendation reasons:",
    ]
    _append_bullets(lines, details.recommendation_reasons)
    lines.append(f"PlayItems ({len(details.play_items)}):")
    for item in details.play_items:
        lines.extend(
            (
                f"  [{item.index}] clip={item.clip_id} codec={item.codec_id}",
                f"    source_45k={item.in_time_45k}..{item.out_time_45k}",
                "    logical_90k="
                f"{item.logical_start_90k}..{item.logical_end_90k} "
                f"duration={item.duration_90k}",
                f"    connection={item.connection_condition} "
                f"multi_angle={_yes_no(item.is_multi_angle)} "
                f"selected_angle={item.selected_angle} angles={item.angle_count}",
                f"    references: m2ts={_yes_no(item.m2ts_exists)} "
                f"clpi={_yes_no(item.clpi_exists)}",
                f"    primary PG streams ({len(item.primary_pg_streams)}):",
            )
        )
        for stream in item.primary_pg_streams:
            lines.append(
                "      "
                f"pid={_optional(stream.pid)} language={_optional(stream.language)} "
                f"coding_type={_optional(stream.coding_type)}"
            )
        if not item.primary_pg_streams:
            lines.append("      (none)")
    if not details.play_items:
        lines.append("  (none)")
    lines.append(f"Marks ({len(details.marks)}):")
    for mark in details.marks:
        lines.append(
            f"  [{mark.index}] type={mark.mark_type} play_item={mark.play_item_index} "
            f"source_45k={mark.timestamp_45k} time_90k={_optional(mark.time_90k)} "
            f"entry_es_pid={_optional(mark.entry_es_pid)} "
            f"duration_45k={_optional(mark.duration_45k)}"
        )
    if not details.marks:
        lines.append("  (none)")
    lines.append(f"Timeline fingerprint ({len(details.timeline_fingerprint)}):")
    for clip_id, in_time, out_time, selected_angle in details.timeline_fingerprint:
        lines.append(f"  {clip_id}: {in_time}..{out_time}, angle={selected_angle}")
    if not details.timeline_fingerprint:
        lines.append("  (none)")
    lines.append("Warnings:")
    _append_bullets(lines, details.warnings)
    lines.append("Errors:")
    _append_bullets(lines, details.errors)
    return "\n".join(lines)


def format_subtitle_details(details: SubtitleDetailsDisplay) -> str:
    """Format source-subtitle details without reading or mutating the source file."""

    resolution = (
        f"{details.play_res_x}x{details.play_res_y}"
        if details.play_res_x is not None and details.play_res_y is not None
        else "unknown"
    )
    lines = [
        f"Subtitle: {details.filename}",
        f"Path: {details.path}",
        f"Format: {details.format}",
        f"Encoding: {_optional(details.encoding)}",
        f"BOM: {_yes_no(details.bom)}",
        f"Event count: {details.event_count}",
        f"Style count: {details.style_count}",
        f"Earliest start: {format_ticks_90k(details.earliest_start_90k)}",
        f"Raw end: {format_ticks_90k(details.raw_end_90k)}",
        f"Effective end: {format_ticks_90k(details.effective_end_90k)}",
        f"Suspected long tail: {_yes_no(details.suspected_long_tail)}",
        f"Duration estimated: {_yes_no(details.duration_estimated)}",
        f"PlayRes: {resolution}",
        f"Font attachments ({len(details.font_attachment_names)}):",
    ]
    _append_bullets(lines, details.font_attachment_names)
    lines.append(f"Graphic attachments ({len(details.graphic_attachment_names)}):")
    _append_bullets(lines, details.graphic_attachment_names)
    lines.extend(
        (
            f"Aegisub Extradata: {_yes_no(details.has_aegisub_extradata)} "
            f"({details.aegisub_extradata_entry_count} entries)",
            f"Sections ({len(details.sections)}):",
        )
    )
    for section in details.sections:
        lines.append(
            f"  {section.name} [{section.normalized_name}]: {section.entry_count} entries"
        )
    if not details.sections:
        lines.append("  (none)")
    lines.append(f"PGS packets: {details.pgs_packet_count}")
    lines.append(f"PGS segment types ({len(details.pgs_segments)}):")
    for segment in details.pgs_segments:
        lines.append(
            f"  0x{segment.segment_type:02X} {segment.name}: {segment.packet_count} packets"
        )
    if not details.pgs_segments:
        lines.append("  (none)")
    lines.append(f"Warnings ({details.warning_count}):")
    _append_bullets(lines, details.warnings)
    return "\n".join(lines)


def _attachment_names(document: AssDocument, section_name: str, marker: str) -> tuple[str, ...]:
    section = document.section(section_name)
    if section is None:
        return ()
    names: list[str] = []
    for entry in section.entries:
        text = _ass_entry_text(entry)
        key, separator, value = text.partition(":")
        if separator and key.strip().casefold() == marker and value.strip():
            names.append(value.strip())
    return tuple(names)


def _ass_entry_text(entry: AssEntry) -> str:
    if isinstance(entry, AssRawLine):
        return entry.text
    return entry.serialize()


def _pgs_segment_summary(document: PgsDocument) -> tuple[PgsSegmentDisplay, ...]:
    counts = Counter(packet.segment_type for packet in document.packets)
    return tuple(
        PgsSegmentDisplay(segment_type, _pgs_segment_name(segment_type), count)
        for segment_type, count in sorted(counts.items())
    )


def _pgs_segment_name(segment_type: int) -> str:
    try:
        member = PgsSegmentType(segment_type)
    except ValueError:
        return "unknown"
    return member.name.replace("_", " ").casefold()


def _append_bullets(lines: list[str], values: tuple[str, ...]) -> None:
    if values:
        lines.extend(f"  - {value}" for value in values)
    else:
        lines.append("  (none)")


def _optional(value: object | None) -> str:
    return "unknown" if value is None else str(value)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
