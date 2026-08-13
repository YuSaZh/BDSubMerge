"""Project-owned ASS/SSA document model and loss-aware parser."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from bdsubmerge.cancellation import CancellationCheck, raise_if_cancelled

TICKS_PER_CENTISECOND = 900


class AssParseError(ValueError):
    """Raised when a recognized ASS structure cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class AssRawLine:
    """A line whose semantics are unknown or intentionally left untouched."""

    text: str


@dataclass(frozen=True, slots=True)
class AssFormatLine:
    fields: tuple[str, ...]
    prefix: str = "Format: "

    def serialize(self) -> str:
        return f"{self.prefix}{','.join(self.fields)}"


@dataclass(frozen=True, slots=True)
class AssKeyValue:
    key: str
    value: str
    separator: str = ": "

    def serialize(self) -> str:
        return f"{self.key}{self.separator}{self.value}"


def _field_index(fields: tuple[str, ...], name: str) -> int | None:
    wanted = name.casefold()
    for index, field in enumerate(fields):
        if field.strip().casefold() == wanted:
            return index
    return None


@dataclass(frozen=True, slots=True)
class AssStyle:
    kind: str
    format_fields: tuple[str, ...]
    values: tuple[str, ...]
    separator: str = " "

    def value(self, field: str) -> str | None:
        index = _field_index(self.format_fields, field)
        return self.values[index] if index is not None and index < len(self.values) else None

    @property
    def name(self) -> str:
        value = self.value("Name")
        if value is None:
            raise AssParseError("style Format declaration has no Name field")
        return value

    def with_value(self, field: str, value: str) -> AssStyle:
        index = _field_index(self.format_fields, field)
        if index is None:
            raise AssParseError(f"style Format declaration has no {field} field")
        values = list(self.values)
        values[index] = value
        return replace(self, values=tuple(values))

    def remap(self, fields: tuple[str, ...]) -> AssStyle:
        values = tuple(self.value(field) or "" for field in fields)
        return replace(self, format_fields=fields, values=values)

    def definition(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                (field.strip().casefold(), value)
                for field, value in zip(self.format_fields, self.values, strict=True)
                if field.strip().casefold() != "name"
            )
        )

    def serialize(self) -> str:
        return f"{self.kind}:{self.separator}{','.join(self.values)}"


_ASS_TIME_RE = re.compile(
    r"^(?P<hours>\d+):(?P<minutes>[0-5]?\d):(?P<seconds>[0-5]?\d)\.(?P<centis>\d{1,2})$"
)


def parse_ass_time(value: str) -> int:
    """Parse an ASS/SSA timestamp into integer 90 kHz ticks."""

    match = _ASS_TIME_RE.fullmatch(value.strip())
    if match is None:
        raise AssParseError(f"invalid ASS timestamp: {value!r}")
    centis_text = match.group("centis")
    centis = int(centis_text) * (10 if len(centis_text) == 1 else 1)
    total_centis = (
        int(match.group("hours")) * 360_000
        + int(match.group("minutes")) * 6_000
        + int(match.group("seconds")) * 100
        + centis
    )
    return total_centis * TICKS_PER_CENTISECOND


def _ceil_div(value: int, divisor: int) -> int:
    return -(-value // divisor)


def format_ass_time(ticks: int, *, is_end: bool = False, start_ticks: int | None = None) -> str:
    """Format ticks using outward ASS centisecond rounding."""

    if ticks < 0:
        raise ValueError("ASS timestamps cannot be negative")
    units = _ceil_div(ticks, TICKS_PER_CENTISECOND) if is_end else ticks // TICKS_PER_CENTISECOND
    if is_end and start_ticks is not None:
        start_units = max(0, start_ticks) // TICKS_PER_CENTISECOND
        units = max(units, start_units + 1)
    hours, remainder = divmod(units, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


@dataclass(frozen=True, slots=True)
class AssEvent:
    kind: str
    format_fields: tuple[str, ...]
    values: tuple[str, ...]
    start_ticks: int
    end_ticks: int
    separator: str = " "

    def value(self, field: str) -> str | None:
        index = _field_index(self.format_fields, field)
        return self.values[index] if index is not None and index < len(self.values) else None

    def with_value(self, field: str, value: str) -> AssEvent:
        index = _field_index(self.format_fields, field)
        if index is None:
            raise AssParseError(f"event Format declaration has no {field} field")
        values = list(self.values)
        values[index] = value
        return replace(self, values=tuple(values))

    def with_times(self, start_ticks: int, end_ticks: int) -> AssEvent:
        if end_ticks < start_ticks:
            raise ValueError("event end precedes event start")
        return replace(self, start_ticks=start_ticks, end_ticks=end_ticks)

    def remap(self, fields: tuple[str, ...]) -> AssEvent:
        values = tuple(self.value(field) or "" for field in fields)
        return replace(self, format_fields=fields, values=values)

    def serialize(self) -> str:
        values = list(self.values)
        start_index = _field_index(self.format_fields, "Start")
        end_index = _field_index(self.format_fields, "End")
        if start_index is None or end_index is None:
            raise AssParseError("event Format declaration must contain Start and End")
        values[start_index] = format_ass_time(self.start_ticks)
        values[end_index] = format_ass_time(
            self.end_ticks,
            is_end=True,
            start_ticks=self.start_ticks,
        )
        return f"{self.kind}:{self.separator}{','.join(values)}"


type AssEntry = AssRawLine | AssFormatLine | AssKeyValue | AssStyle | AssEvent


@dataclass(frozen=True, slots=True)
class AssSection:
    name: str
    header: str
    entries: tuple[AssEntry, ...]

    @property
    def normalized_name(self) -> str:
        return self.name.strip().casefold()

    def serialize_lines(
        self,
        *,
        cancellation_check: CancellationCheck | None = None,
    ) -> tuple[str, ...]:
        lines = [self.header]
        for entry in self.entries:
            raise_if_cancelled(cancellation_check)
            if isinstance(entry, AssRawLine):
                lines.append(entry.text)
            else:
                lines.append(entry.serialize())
        return tuple(lines)


@dataclass(frozen=True, slots=True)
class AssDocument:
    preamble: tuple[str, ...]
    sections: tuple[AssSection, ...]
    newline: str = "\n"
    trailing_newline: bool = True
    bom: bool = False

    def section(self, name: str) -> AssSection | None:
        wanted = name.strip().casefold()
        return next(
            (section for section in self.sections if section.normalized_name == wanted),
            None,
        )

    @property
    def events(self) -> tuple[AssEvent, ...]:
        return tuple(
            entry
            for section in self.sections
            if section.normalized_name == "events"
            for entry in section.entries
            if isinstance(entry, AssEvent)
        )

    @property
    def styles(self) -> tuple[AssStyle, ...]:
        return tuple(
            entry
            for section in self.sections
            if section.normalized_name in {"v4 styles", "v4+ styles"}
            for entry in section.entries
            if isinstance(entry, AssStyle)
        )

    @property
    def script_info(self) -> tuple[AssKeyValue, ...]:
        section = self.section("Script Info")
        if section is None:
            return ()
        return tuple(entry for entry in section.entries if isinstance(entry, AssKeyValue))

    def serialize(
        self,
        *,
        cancellation_check: CancellationCheck | None = None,
    ) -> str:
        lines = list(self.preamble)
        for section in self.sections:
            raise_if_cancelled(cancellation_check)
            lines.extend(
                section.serialize_lines(cancellation_check=cancellation_check)
            )
        text = self.newline.join(lines)
        if self.trailing_newline:
            text += self.newline
        return ("\ufeff" if self.bom else "") + text

    def to_bytes(
        self,
        *,
        encoding: str = "utf-8",
        bom: bool | None = None,
        cancellation_check: CancellationCheck | None = None,
    ) -> bytes:
        include_bom = self.bom if bom is None else bom
        text = replace(self, bom=False).serialize(
            cancellation_check=cancellation_check
        )
        if encoding.casefold().replace("_", "-") == "utf-8":
            return ((b"\xef\xbb\xbf" if include_bom else b"") + text.encode("utf-8"))
        return text.encode(encoding)


_SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")


def _split_lines(text: str) -> tuple[list[str], str, bool, bool]:
    bom = text.startswith("\ufeff")
    if bom:
        text = text[1:]
    newline = "\r\n" if "\r\n" in text else "\n"
    trailing_newline = text.endswith(("\r", "\n"))
    return text.splitlines(), newline, trailing_newline, bom


def _prefix_parts(line: str) -> tuple[str, str, str] | None:
    colon = line.find(":")
    if colon < 0:
        return None
    key = line[:colon]
    rest = line[colon + 1 :]
    whitespace_length = len(rest) - len(rest.lstrip(" \t"))
    separator = rest[:whitespace_length]
    return key, separator, rest[whitespace_length:]


def _parse_record_values(payload: str, fields: tuple[str, ...]) -> tuple[str, ...]:
    field_count = len(fields)
    if not fields:
        raise AssParseError("empty Format declaration")
    text_index = _field_index(fields, "Text")
    if text_index is None:
        values = tuple(payload.split(",", maxsplit=field_count - 1))
    else:
        left = payload.split(",", maxsplit=text_index)
        if len(left) != text_index + 1:
            values = tuple(left)
        else:
            prefix = left[:-1]
            remaining = left[-1]
            fields_after_text = field_count - text_index - 1
            suffix_split = remaining.rsplit(",", maxsplit=fields_after_text)
            values = (*prefix, *suffix_split)
    if len(values) != field_count:
        raise AssParseError(
            f"record has {len(values)} values but its Format declaration has {field_count} fields"
        )
    return values


def _parse_section_entries(
    name: str,
    lines: list[str],
    cancellation_check: CancellationCheck | None = None,
) -> tuple[AssEntry, ...]:
    normalized = name.strip().casefold()
    active_format: tuple[str, ...] | None = None
    result: list[AssEntry] = []
    for line in lines:
        raise_if_cancelled(cancellation_check)
        parts = _prefix_parts(line)
        if parts is None:
            result.append(AssRawLine(line))
            continue
        key, separator, payload = parts
        key_normalized = key.strip().casefold()
        if key_normalized == "format" and normalized in {"events", "v4 styles", "v4+ styles"}:
            active_format = tuple(field.strip() for field in payload.split(","))
            result.append(AssFormatLine(active_format, prefix=f"{key}:{separator}"))
            continue
        if normalized in {"v4 styles", "v4+ styles"} and key_normalized == "style":
            if active_format is None:
                raise AssParseError("Style record encountered before Format declaration")
            values = _parse_record_values(payload, active_format)
            result.append(AssStyle(key, active_format, values, separator))
            continue
        if normalized == "events" and key_normalized in {"dialogue", "comment"}:
            if active_format is None:
                raise AssParseError(f"{key} record encountered before Format declaration")
            values = _parse_record_values(payload, active_format)
            start_index = _field_index(active_format, "Start")
            end_index = _field_index(active_format, "End")
            if start_index is None or end_index is None:
                raise AssParseError("event Format declaration must contain Start and End")
            result.append(
                AssEvent(
                    key,
                    active_format,
                    values,
                    parse_ass_time(values[start_index]),
                    parse_ass_time(values[end_index]),
                    separator,
                )
            )
            continue
        if normalized == "script info":
            result.append(AssKeyValue(key, payload, f":{separator}"))
        else:
            result.append(AssRawLine(line))
    return tuple(result)


def parse_ass(
    text: str,
    *,
    cancellation_check: CancellationCheck | None = None,
) -> AssDocument:
    """Parse ASS/SSA without discarding unrecognized sections or records."""

    lines, newline, trailing_newline, bom = _split_lines(text)
    preamble: list[str] = []
    raw_sections: list[tuple[str, str, list[str]]] = []
    current: tuple[str, str, list[str]] | None = None
    for line in lines:
        raise_if_cancelled(cancellation_check)
        section_match = _SECTION_RE.fullmatch(line)
        if section_match is not None:
            current = (section_match.group("name"), line, [])
            raw_sections.append(current)
        elif current is None:
            preamble.append(line)
        else:
            current[2].append(line)
    sections: list[AssSection] = []
    for name, header, body in raw_sections:
        raise_if_cancelled(cancellation_check)
        sections.append(
            AssSection(
                name,
                header,
                _parse_section_entries(name, body, cancellation_check),
            )
        )
    return AssDocument(tuple(preamble), tuple(sections), newline, trailing_newline, bom)
