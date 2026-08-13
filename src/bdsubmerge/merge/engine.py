"""Pure text-subtitle merge services."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from itertools import pairwise

from bdsubmerge.cancellation import (
    CancellationCheck,
    cancellation_scope,
    raise_if_cancelled,
    report_progress,
)
from bdsubmerge.subtitles.ass_document import (
    AssDocument,
    AssEntry,
    AssEvent,
    AssFormatLine,
    AssRawLine,
    AssSection,
    AssStyle,
)
from bdsubmerge.subtitles.srt_document import SrtCue, SrtDocument
from bdsubmerge.subtitles.style_merger import merge_style_set

from .plan import MergeOptions, MergePlan, MergeSource
from .report import MergeNotice, MergeReport, StyleRenameRecord


class MergeConflictError(ValueError):
    """Raised when a conflict requires an explicit user decision."""


@dataclass(frozen=True, slots=True)
class AssMergeResult:
    document: AssDocument
    report: MergeReport


@dataclass(frozen=True, slots=True)
class SrtMergeResult:
    document: SrtDocument
    report: MergeReport


_SCRIPT_INFO_KEYS = (
    "PlayResX",
    "PlayResY",
    "WrapStyle",
    "ScaledBorderAndShadow",
    "YCbCr Matrix",
    "Timer",
)
_BLOCKING_SCRIPT_INFO_KEYS = {"playresx", "playresy"}
_CORE_SECTIONS = {"script info", "v4 styles", "v4+ styles", "events"}
_KNOWN_MERGED_SECTIONS = {"aegisub extradata", "fonts", "graphics"}


def _script_info_map(document: AssDocument) -> dict[str, tuple[str, str]]:
    return {entry.key.casefold(): (entry.key, entry.value) for entry in document.script_info}


def _script_info_notices(
    base: AssDocument,
    source: MergeSource[AssDocument],
) -> tuple[MergeNotice, ...]:
    base_values = _script_info_map(base)
    incoming_values = _script_info_map(source.document)
    notices: list[MergeNotice] = []
    for key in _SCRIPT_INFO_KEYS:
        base_value = base_values.get(key.casefold())
        incoming_value = incoming_values.get(key.casefold())
        if base_value is None or incoming_value is None or base_value[1] == incoming_value[1]:
            continue
        severity = "error" if key.casefold() in _BLOCKING_SCRIPT_INFO_KEYS else "warning"
        notices.append(
            MergeNotice(
                severity,
                "script_info_conflict",
                f"{key} differs: base={base_value[1]!r}, source={incoming_value[1]!r}",
                source.label,
            )
        )
    return tuple(notices)


def _ordered_union(fields: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    result: list[str] = []
    present: set[str] = set()
    for field_set in fields:
        for field in field_set:
            folded = field.casefold()
            if folded not in present:
                result.append(field)
                present.add(folded)
    return tuple(result)


def _shift_ass_event(
    event: AssEvent,
    source: MergeSource[AssDocument],
    options: MergeOptions,
) -> tuple[AssEvent | None, tuple[MergeNotice, ...], bool]:
    start = event.start_ticks + source.offset_ticks
    end = event.end_ticks + source.offset_ticks
    notices: list[MergeNotice] = []
    clipped = False
    if end < start:
        raise MergeConflictError(f"event end precedes start after shifting source {source.label}")
    if end <= 0 and not options.keep_events_ending_before_zero:
        notices.append(
            MergeNotice(
                "warning",
                "event_dropped_before_zero",
                "event ends at or before zero",
                source.label,
            )
        )
        return None, tuple(notices), clipped
    if start < 0 < end and options.clip_negative_starts:
        start = 0
        clipped = True
        notices.append(
            MergeNotice(
                "warning",
                "event_start_clipped",
                "negative event start clipped to zero",
                source.label,
            )
        )
    if start < 0:
        raise MergeConflictError(
            f"source {source.label} contains an event with an unrepresentable negative start"
        )
    playlist_end = options.playlist_end_ticks
    if playlist_end is not None and end > playlist_end:
        severity = "error" if start > playlist_end else "warning"
        code = (
            "event_starts_after_playlist"
            if start > playlist_end
            else "event_ends_after_playlist"
        )
        notices.append(MergeNotice(severity, code, "event exceeds playlist end", source.label))
    return event.with_times(start, end), tuple(notices), clipped


def _find_section(document: AssDocument, names: set[str]) -> AssSection | None:
    return next(
        (section for section in document.sections if section.normalized_name in names),
        None,
    )


def _replace_structured_section(
    section: AssSection,
    records: tuple[AssStyle | AssEvent, ...],
    fields: tuple[str, ...],
) -> AssSection:
    result: list[AssEntry] = []
    inserted = False
    for entry in section.entries:
        raise_if_cancelled()
        if isinstance(entry, AssFormatLine):
            if not inserted:
                result.append(replace(entry, fields=fields))
                result.extend(record.remap(fields) for record in records)
                inserted = True
            continue
        if isinstance(entry, (AssStyle, AssEvent)):
            continue
        result.append(entry)
    if not inserted:
        result.insert(0, AssFormatLine(fields))
        result[1:1] = [record.remap(fields) for record in records]
    return replace(section, entries=tuple(result))


def _unknown_section_notices(
    sources: tuple[MergeSource[AssDocument], ...],
) -> tuple[MergeNotice, ...]:
    seen: dict[str, tuple[str, ...]] = {}
    notices: list[MergeNotice] = []
    for source in sources:
        raise_if_cancelled()
        for section in source.document.sections:
            raise_if_cancelled()
            name = section.normalized_name
            if name in _CORE_SECTIONS or name in _KNOWN_MERGED_SECTIONS:
                continue
            content = section.serialize_lines()[1:]
            previous = seen.get(name)
            if previous is not None and previous != content:
                notices.append(
                    MergeNotice(
                        "warning",
                        "unknown_section_conflict",
                        f"custom section [{section.name}] has differing content and was preserved",
                        source.label,
                    )
                )
            seen.setdefault(name, content)
    return tuple(notices)


@dataclass(frozen=True, slots=True)
class _Attachment:
    name: str
    lines: tuple[str, ...]

    @property
    def digest(self) -> str:
        return hashlib.sha256("\n".join(self.lines).encode("utf-8")).hexdigest()


def _parse_attachments(section: AssSection) -> tuple[_Attachment, ...]:
    attachments: list[_Attachment] = []
    current_name: str | None = None
    current_lines: list[str] = []
    for entry in section.entries:
        raise_if_cancelled()
        line = entry.text if isinstance(entry, AssRawLine) else entry.serialize()
        if ":" in line and line.split(":", 1)[0].strip().casefold() in {"fontname", "filename"}:
            if current_name is not None:
                attachments.append(_Attachment(current_name, tuple(current_lines)))
            current_name = line.split(":", 1)[1].strip()
            current_lines = [line]
        elif current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        attachments.append(_Attachment(current_name, tuple(current_lines)))
    return tuple(attachments)


def _rename_attachment(attachment: _Attachment, new_name: str) -> _Attachment:
    key = attachment.lines[0].split(":", 1)[0]
    return _Attachment(new_name, (f"{key}: {new_name}", *attachment.lines[1:]))


def _merged_attachment_section(
    sources: tuple[MergeSource[AssDocument], ...],
    section_name: str,
    notices: list[MergeNotice],
) -> tuple[AssSection | None, int]:
    attachments: list[_Attachment] = []
    by_name: dict[str, list[_Attachment]] = {}
    deduplicated = 0
    header = f"[{section_name.title()}]"
    for source in sources:
        raise_if_cancelled()
        report_progress(70, source.detail or source.label)
        section = source.document.section(section_name)
        if section is None:
            continue
        header = section.header if not attachments else header
        for attachment in _parse_attachments(section):
            raise_if_cancelled()
            matches = by_name.get(attachment.name.casefold(), [])
            if any(match.digest == attachment.digest for match in matches):
                deduplicated += 1
                continue
            if matches:
                stem = f"{attachment.name}__{source.label}"
                new_name = stem
                suffix = 2
                while new_name.casefold() in by_name:
                    new_name = f"{stem}_{suffix}"
                    suffix += 1
                notices.append(
                    MergeNotice(
                        "warning",
                        "attachment_renamed",
                        f"attachment {attachment.name!r} renamed to {new_name!r}",
                        source.label,
                    )
                )
                attachment = _rename_attachment(attachment, new_name)
            attachments.append(attachment)
            by_name.setdefault(attachment.name.casefold(), []).append(attachment)
    if not attachments:
        return None, deduplicated
    entries = tuple(AssRawLine(line) for attachment in attachments for line in attachment.lines)
    return AssSection(section_name, header, entries), deduplicated


_EXTRADATA_RE = re.compile(r"^(?P<prefix>Data:\s*)(?P<id>\d+)(?P<tail>,.*)$", re.IGNORECASE)


def _merge_extradata(
    sources: tuple[MergeSource[AssDocument], ...],
    events_by_source: list[list[AssEvent]],
    notices: list[MergeNotice],
) -> AssSection | None:
    content_to_id: dict[str, int] = {}
    used_ids: set[int] = set()
    lines: list[str] = []
    header = "[Aegisub Extradata]"
    for source_index, source in enumerate(sources):
        raise_if_cancelled()
        section = source.document.section("Aegisub Extradata")
        if section is None:
            continue
        header = section.header if not lines else header
        id_map: dict[int, int] = {}
        for entry in section.entries:
            raise_if_cancelled()
            line = entry.text if isinstance(entry, AssRawLine) else entry.serialize()
            match = _EXTRADATA_RE.fullmatch(line)
            if match is None:
                lines.append(line)
                continue
            old_id = int(match.group("id"))
            content = match.group("tail")
            if content in content_to_id:
                new_id = content_to_id[content]
            elif old_id not in used_ids:
                new_id = old_id
            else:
                new_id = max(used_ids, default=-1) + 1
                notices.append(
                    MergeNotice(
                        "warning",
                        "extradata_id_remapped",
                        f"Extradata ID {old_id} remapped to {new_id}",
                        source.label,
                    )
                )
            id_map[old_id] = new_id
            if content not in content_to_id:
                content_to_id[content] = new_id
                used_ids.add(new_id)
                lines.append(f"{match.group('prefix')}{new_id}{content}")
        if id_map:
            events_by_source[source_index] = [
                _remap_event_extradata(event, id_map)
                for event in events_by_source[source_index]
            ]
    if not lines:
        return None
    return AssSection("Aegisub Extradata", header, tuple(AssRawLine(line) for line in lines))


def _remap_event_extradata(event: AssEvent, id_map: dict[int, int]) -> AssEvent:
    extra = event.value("Extra")
    if extra is None or not extra.strip():
        return event
    pieces = re.split(r"([,;])", extra)
    for index in range(0, len(pieces), 2):
        token = pieces[index]
        stripped = token.strip()
        if stripped.isdigit() and int(stripped) in id_map:
            pieces[index] = token.replace(stripped, str(id_map[int(stripped)]), 1)
    return event.with_value("Extra", "".join(pieces))


def merge_ass(
    plan: MergePlan[AssDocument],
    *,
    cancellation_check: CancellationCheck | None = None,
) -> AssMergeResult:
    """Merge ASS/SSA sources without choosing or writing an output path."""

    with cancellation_scope(cancellation_check):
        return _merge_ass(plan)


def _merge_ass(plan: MergePlan[AssDocument]) -> AssMergeResult:
    raise_if_cancelled()

    sources = plan.sources
    base = sources[0].document
    notices: list[MergeNotice] = list(_unknown_section_notices(sources))
    for source in sources[1:]:
        raise_if_cancelled()
        notices.extend(_script_info_notices(base, source))
    blocking = [notice for notice in notices if notice.severity == "error"]
    if blocking and not plan.options.accept_script_info_conflicts:
        details = "; ".join(notice.message for notice in blocking)
        raise MergeConflictError(f"Script Info conflict requires explicit acceptance: {details}")

    style_sections = [
        _find_section(source.document, {"v4 styles", "v4+ styles"})
        for source in sources
    ]
    base_style_section = style_sections[0]
    if base_style_section is None:
        raise MergeConflictError("base ASS document has no style section")
    incompatible = [
        source.label
        for source, section in zip(sources, style_sections, strict=True)
        if section is not None and section.normalized_name != base_style_section.normalized_name
    ]
    if incompatible:
        raise MergeConflictError(f"cannot mix ASS V4+ and SSA V4 style sections: {incompatible}")

    styles: tuple[AssStyle, ...] = ()
    events_by_source: list[list[AssEvent]] = []
    rename_records: list[StyleRenameRecord] = []
    dropped = 0
    clipped = 0
    source_count = len(sources)
    for source_index, source in enumerate(sources):
        raise_if_cancelled()
        report_progress(
            35 + (source_index * 30 // source_count),
            source.detail or source.label,
        )
        shifted_events: list[AssEvent] = []
        for event in source.document.events:
            raise_if_cancelled()
            shifted, event_notices, was_clipped = _shift_ass_event(event, source, plan.options)
            notices.extend(event_notices)
            clipped += int(was_clipped)
            if shifted is None:
                dropped += 1
            else:
                shifted_events.append(shifted)
        style_result = merge_style_set(
            styles,
            source.document.styles,
            tuple(shifted_events),
            source_label=source.label,
        )
        styles = style_result.styles
        events_by_source.append(list(style_result.events))
        rename_records.extend(
            StyleRenameRecord(rename.source_label, rename.old_name, rename.new_name)
            for rename in style_result.renames
        )

    extradata_section = _merge_extradata(sources, events_by_source, notices)
    events = tuple(event for source_events in events_by_source for event in source_events)
    style_fields = _ordered_union(tuple(style.format_fields for style in styles))
    event_fields = _ordered_union(tuple(event.format_fields for event in events))
    if not style_fields or not event_fields:
        raise MergeConflictError("ASS merge requires style and event Format declarations")
    base_event_section = base.section("Events")
    if base_event_section is None:
        raise MergeConflictError("base ASS document has no Events section")

    replacements: dict[str, AssSection] = {
        base_style_section.normalized_name: _replace_structured_section(
            base_style_section, styles, style_fields
        ),
        "events": _replace_structured_section(base_event_section, events, event_fields),
    }
    if extradata_section is not None:
        replacements["aegisub extradata"] = extradata_section
    attachment_deduplicated = 0
    for attachment_name in ("Fonts", "Graphics"):
        raise_if_cancelled()
        attachment_section, deduplicated = _merged_attachment_section(
            sources, attachment_name, notices
        )
        attachment_deduplicated += deduplicated
        if attachment_section is not None:
            replacements[attachment_name.casefold()] = attachment_section

    sections: list[AssSection] = []
    emitted: set[str] = set()
    for section in base.sections:
        raise_if_cancelled()
        replacement = replacements.get(section.normalized_name)
        sections.append(replacement or section)
        emitted.add(section.normalized_name)
    for key, section in replacements.items():
        raise_if_cancelled()
        if key not in emitted:
            sections.append(section)
            emitted.add(key)
    for source in sources[1:]:
        raise_if_cancelled()
        for section in source.document.sections:
            raise_if_cancelled()
            if section.normalized_name not in _CORE_SECTIONS | _KNOWN_MERGED_SECTIONS:
                sections.append(section)

    document = replace(base, sections=tuple(sections))
    report = MergeReport(
        tuple(source.label for source in sources),
        sum(len(source.document.events) for source in sources),
        len(events),
        dropped,
        clipped,
        tuple(rename_records),
        tuple(notices),
        attachment_deduplicated_count=attachment_deduplicated,
    )
    return AssMergeResult(document, report)


def merge_srt(
    plan: MergePlan[SrtDocument],
    *,
    cancellation_check: CancellationCheck | None = None,
) -> SrtMergeResult:
    with cancellation_scope(cancellation_check):
        return _merge_srt(plan)


def _merge_srt(plan: MergePlan[SrtDocument]) -> SrtMergeResult:
    raise_if_cancelled()
    cues: list[SrtCue] = []
    notices: list[MergeNotice] = []
    dropped = 0
    clipped = 0
    source_count = len(plan.sources)
    for source_index, source in enumerate(plan.sources):
        raise_if_cancelled()
        report_progress(
            35 + (source_index * 40 // source_count),
            source.detail or source.label,
        )
        for cue in source.document.cues:
            raise_if_cancelled()
            start = cue.start_ticks + source.offset_ticks
            end = cue.end_ticks + source.offset_ticks
            if end <= 0 and not plan.options.keep_events_ending_before_zero:
                dropped += 1
                notices.append(
                    MergeNotice(
                        "warning",
                        "cue_dropped_before_zero",
                        "cue ends at or before zero",
                        source.label,
                    )
                )
                continue
            if start < 0 < end and plan.options.clip_negative_starts:
                start = 0
                clipped += 1
                notices.append(
                    MergeNotice(
                        "warning",
                        "cue_start_clipped",
                        "negative cue start clipped to zero",
                        source.label,
                    )
                )
            if start < 0:
                raise MergeConflictError(
                    f"source {source.label} contains a cue with a negative start"
                )
            playlist_end = plan.options.playlist_end_ticks
            if playlist_end is not None and end > playlist_end:
                severity = "error" if start > playlist_end else "warning"
                notices.append(
                    MergeNotice(
                        severity,
                        "cue_outside_playlist",
                        "cue exceeds playlist end",
                        source.label,
                    )
                )
            cues.append(replace(cue, start_ticks=start, end_ticks=end))
    for previous, current in pairwise(cues):
        raise_if_cancelled()
        if current.start_ticks < previous.end_ticks:
            notices.append(MergeNotice("warning", "cue_overlap", "SRT cues overlap"))
    base = plan.sources[0].document
    document = replace(base, cues=tuple(cues), bom=True)
    report = MergeReport(
        tuple(source.label for source in plan.sources),
        sum(len(source.document.cues) for source in plan.sources),
        len(cues),
        dropped,
        clipped,
        notices=tuple(notices),
    )
    return SrtMergeResult(document, report)
