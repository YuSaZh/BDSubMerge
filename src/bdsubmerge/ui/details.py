"""Localized, read-only detail views for application display projections."""

from __future__ import annotations

import re
from collections.abc import Callable

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bdsubmerge.application.display_models import (
    PlaylistStructureDisplay,
    SubtitleDetailsDisplay,
)
from bdsubmerge.domain.timebase import TICKS_PER_SECOND

TranslationLookup = Callable[..., str]


class ReadOnlyDetailsDialog(QDialog):
    """Non-modal diagnostic detail window that never touches source media."""

    def __init__(
        self,
        title: str,
        text: str,
        close_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.resize(760, 600)

        layout = QVBoxLayout(self)
        self.details = QPlainTextEdit(text)
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.details.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.details)

        actions = QHBoxLayout()
        actions.addStretch()
        close_button = QPushButton(close_text)
        close_button.clicked.connect(self.reject)
        actions.addWidget(close_button)
        layout.addLayout(actions)


def format_playlist_details(
    details: PlaylistStructureDisplay,
    tr: TranslationLookup,
) -> str:
    """Render a complete playlist projection using UI-owned translations."""

    lines = [
        _field(tr, "details.path", details.path),
        _field(tr, "details.duration", _format_ticks(details.duration_90k, tr)),
        _field(tr, "details.available", _yes_no(details.is_available, tr)),
        _field(tr, "details.score", details.score),
        _field(tr, "details.confidence", details.confidence),
        _field(tr, "details.unique_clips", details.unique_clip_count),
        _field(tr, "details.repeated_clips", details.repeated_clip_count),
        _field(
            tr,
            "details.repeated_ratio",
            _format_per_mille(details.repeated_clip_ratio_per_mille),
        ),
        _field(tr, "details.multi_angle", _yes_no(details.has_multi_angle, tr)),
        _field(
            tr,
            "details.references_complete",
            _yes_no(details.references_complete, tr),
        ),
        "",
        tr("details.recommendation_reasons"),
    ]
    _append_bullets(
        lines,
        tuple(
            _localize_playlist_message(value, tr)
            for value in details.recommendation_reasons
        ),
        tr,
    )
    lines.extend(("", tr("details.play_items", count=len(details.play_items))))
    for item in details.play_items:
        lines.extend(
            (
                tr(
                    "details.play_item",
                    index=item.index,
                    clip=item.clip_id,
                    codec=item.codec_id,
                    duration=_format_ticks(item.duration_90k, tr),
                ),
                tr(
                    "details.source_range",
                    start=item.in_time_45k,
                    end=item.out_time_45k,
                ),
                tr(
                    "details.logical_range",
                    start=item.logical_start_90k,
                    end=item.logical_end_90k,
                ),
                tr(
                    "details.connection",
                    condition=item.connection_condition,
                    multi_angle=_yes_no(item.is_multi_angle, tr),
                    selected=item.selected_angle,
                    count=item.angle_count,
                ),
                tr(
                    "details.references",
                    m2ts=_yes_no(item.m2ts_exists, tr),
                    clpi=_yes_no(item.clpi_exists, tr),
                ),
                tr("details.pg_streams", count=len(item.primary_pg_streams)),
            )
        )
        if item.primary_pg_streams:
            lines.extend(
                tr(
                    "details.pg_stream",
                    pid=_optional(stream.pid, tr),
                    language=_optional(stream.language, tr),
                    coding_type=_optional(stream.coding_type, tr),
                )
                for stream in item.primary_pg_streams
            )
        else:
            lines.append(f"  {tr('common.none')}")
    if not details.play_items:
        lines.append(f"  {tr('common.none')}")

    lines.extend(("", tr("details.marks", count=len(details.marks))))
    if details.marks:
        lines.extend(
            tr(
                "details.mark",
                index=mark.index,
                mark_type=mark.mark_type,
                play_item=mark.play_item_index,
                source=mark.timestamp_45k,
                time=_format_ticks(mark.time_90k, tr),
                pid=_optional(mark.entry_es_pid, tr),
                duration=_optional(mark.duration_45k, tr),
            )
            for mark in details.marks
        )
    else:
        lines.append(f"  {tr('common.none')}")

    lines.extend(
        (
            "",
            tr(
                "details.timeline_fingerprint",
                count=len(details.timeline_fingerprint),
            ),
        )
    )
    if details.timeline_fingerprint:
        lines.extend(
            tr(
                "details.timeline_fingerprint_item",
                clip=clip,
                start=start,
                end=end,
                angle=selected_angle,
            )
            for clip, start, end, selected_angle in details.timeline_fingerprint
        )
    else:
        lines.append(f"  {tr('common.none')}")

    lines.extend(("", tr("details.warnings", count=len(details.warnings))))
    _append_bullets(
        lines,
        tuple(_localize_playlist_message(value, tr) for value in details.warnings),
        tr,
    )
    lines.extend(("", tr("details.errors", count=len(details.errors))))
    _append_bullets(
        lines,
        tuple(_localize_playlist_message(value, tr) for value in details.errors),
        tr,
    )
    return "\n".join(lines)


def format_subtitle_details(
    details: SubtitleDetailsDisplay,
    tr: TranslationLookup,
) -> str:
    """Render source-subtitle analysis without reopening the source file."""

    resolution = (
        f"{details.play_res_x}x{details.play_res_y}"
        if details.play_res_x is not None and details.play_res_y is not None
        else tr("common.unknown")
    )
    lines = [
        _field(tr, "details.filename", details.filename),
        _field(tr, "details.path", details.path),
        _field(tr, "details.format", details.format),
        _field(tr, "details.encoding", _optional(details.encoding, tr)),
        _field(tr, "details.bom", _yes_no(details.bom, tr)),
        _field(tr, "details.event_count", details.event_count),
        _field(tr, "details.style_count", details.style_count),
        _field(tr, "details.earliest_start", _format_ticks(details.earliest_start_90k, tr)),
        _field(tr, "details.raw_end", _format_ticks(details.raw_end_90k, tr)),
        _field(tr, "details.effective_end", _format_ticks(details.effective_end_90k, tr)),
        _field(
            tr,
            "details.suspected_long_tail",
            _yes_no(details.suspected_long_tail, tr),
        ),
        _field(
            tr,
            "details.duration_estimated",
            _yes_no(details.duration_estimated, tr),
        ),
        _field(tr, "details.play_res", resolution),
        "",
        tr("details.font_attachments", count=len(details.font_attachment_names)),
    ]
    _append_bullets(lines, details.font_attachment_names, tr)
    lines.extend(
        ("", tr("details.graphic_attachments", count=len(details.graphic_attachment_names)))
    )
    _append_bullets(lines, details.graphic_attachment_names, tr)
    lines.extend(
        (
            "",
            _field(
                tr,
                "details.aegisub_extradata",
                tr(
                    "details.present_with_count",
                    present=_yes_no(details.has_aegisub_extradata, tr),
                    count=details.aegisub_extradata_entry_count,
                ),
            ),
            tr("details.sections", count=len(details.sections)),
        )
    )
    if details.sections:
        lines.extend(
            tr(
                "details.section",
                name=section.name,
                normalized=section.normalized_name,
                count=section.entry_count,
            )
            for section in details.sections
        )
    else:
        lines.append(f"  {tr('common.none')}")
    lines.extend(
        (
            "",
            _field(tr, "details.pgs_packets", details.pgs_packet_count),
            tr("details.pgs_segments", count=len(details.pgs_segments)),
        )
    )
    if details.pgs_segments:
        lines.extend(
            tr(
                "details.pgs_segment",
                segment_type=segment.segment_type,
                name=tr(
                    {
                        0x14: "details.pgs_palette_definition",
                        0x15: "details.pgs_object_definition",
                        0x16: "details.pgs_presentation_composition",
                        0x17: "details.pgs_window_definition",
                        0x80: "details.pgs_end",
                    }.get(segment.segment_type, "details.pgs_unknown")
                ),
                count=segment.packet_count,
            )
            for segment in details.pgs_segments
        )
    else:
        lines.append(f"  {tr('common.none')}")
    lines.extend(("", tr("details.warnings", count=details.warning_count)))
    _append_bullets(lines, details.warnings, tr)
    return "\n".join(lines)


def _field(tr: TranslationLookup, key: str, value: object) -> str:
    return f"{tr(key)}: {value}"


def _format_ticks(value: int | None, tr: TranslationLookup) -> str:
    if value is None:
        return tr("common.unknown")
    sign = "-" if value < 0 else ""
    total_milliseconds = abs(value) * 1_000 // TICKS_PER_SECOND
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    clock = f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    return tr("details.ticks", clock=clock, ticks=value)


def _yes_no(value: bool, tr: TranslationLookup) -> str:
    return tr("common.yes" if value else "common.no")


def _format_per_mille(value: int) -> str:
    whole, decimal = divmod(value, 10)
    return f"{whole}.{decimal}%" if decimal else f"{whole}%"


def _optional(value: object | None, tr: TranslationLookup) -> str:
    return tr("common.unknown") if value is None else str(value)


def _append_bullets(
    lines: list[str],
    values: tuple[str, ...],
    tr: TranslationLookup,
) -> None:
    if values:
        lines.extend(f"  - {value}" for value in values)
    else:
        lines.append(f"  {tr('common.none')}")


_PLAYLIST_MESSAGE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"Repeated clip references reduce score by (?P<penalty>\d+)"),
        "details.reason_repeated_clips",
    ),
    (
        re.compile(
            r"(?P<count>\d+) very short PlayItems reduce score by "
            r"(?P<penalty>\d+)"
        ),
        "details.reason_short_items",
    ),
    (
        re.compile(
            r"Subtitle cumulative duration match contributes (?P<points>\d+) points"
        ),
        "details.reason_subtitle_duration",
    ),
    (
        re.compile(
            r"Episode-boundary count match contributes (?P<points>\d+) points"
        ),
        "details.reason_episode_count",
    ),
    (
        re.compile(r"PlayItem (?P<index>\d+) missing STREAM/(?P<clip>[^/]+)\.m2ts"),
        "details.warning_missing_m2ts",
    ),
    (
        re.compile(r"PlayItem (?P<index>\d+) missing CLIPINF/(?P<clip>[^/]+)\.clpi"),
        "details.warning_missing_clpi",
    ),
    (
        re.compile(
            r"PlayItem (?P<index>\d+) is multi-angle; explicitly selected angle "
            r"(?P<angle>\d+)"
        ),
        "details.warning_multi_angle",
    ),
    (
        re.compile(
            r"Playlist mark (?P<index>\d+) references missing PlayItem "
            r"(?P<play_item>\d+)"
        ),
        "details.error_mark_missing_item",
    ),
    (
        re.compile(r"Playlist mark (?P<index>\d+) is before PlayItem IN time"),
        "details.error_mark_before_in",
    ),
    (
        re.compile(r"Playlist mark (?P<index>\d+) is after PlayItem OUT time"),
        "details.error_mark_after_out",
    ),
    (
        re.compile(
            r"Playlist mark (?P<index>\d+) duplicates an earlier chapter time"
        ),
        "details.warning_duplicate_mark",
    ),
    (
        re.compile(r"Playlist mark (?P<index>\d+) is out of chronological order"),
        "details.warning_mark_order",
    ),
    (
        re.compile(
            r"PlayItem (?P<index>\d+) OUT time must be greater than IN time"
        ),
        "details.error_play_item_range",
    ),
)

_PLAYLIST_MESSAGE_KEYS = {
    "Playlist is unavailable because parsing or validation failed": (
        "details.reason_unavailable"
    ),
    "Duration exceeds the main-feature threshold": "details.reason_feature_duration",
    "Every PlayItem references a unique clip": "details.reason_unique_clips",
    "All referenced M2TS and CLPI files exist": "details.reason_references_complete",
    "Missing referenced M2TS or CLPI files": "details.reason_references_missing",
    "Multi-angle content requires explicit review": "details.reason_multi_angle",
    "Playlist total duration is zero": "details.error_zero_duration",
}


def _localize_playlist_message(value: str, tr: TranslationLookup) -> str:
    key = _PLAYLIST_MESSAGE_KEYS.get(value)
    if key is not None:
        return tr(key)
    for pattern, key in _PLAYLIST_MESSAGE_PATTERNS:
        match = pattern.fullmatch(value)
        if match is not None:
            return tr(key, **match.groupdict())
    return value
