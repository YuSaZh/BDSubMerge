"""Project-owned SRT model using integer 90 kHz timestamps."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

TICKS_PER_MILLISECOND = 90


class SrtParseError(ValueError):
    """Raised for malformed SRT input."""


@dataclass(frozen=True, slots=True)
class SrtCue:
    index: str
    start_ticks: int
    end_ticks: int
    text_lines: tuple[str, ...]
    settings: str = ""

    def shifted(self, offset_ticks: int) -> SrtCue:
        return replace(
            self,
            start_ticks=self.start_ticks + offset_ticks,
            end_ticks=self.end_ticks + offset_ticks,
        )


@dataclass(frozen=True, slots=True)
class SrtDocument:
    cues: tuple[SrtCue, ...]
    newline: str = "\r\n"
    bom: bool = True

    def serialize(self, *, bom: bool | None = None) -> str:
        lines: list[str] = []
        for index, cue in enumerate(self.cues, start=1):
            lines.append(str(index))
            timing = (
                f"{format_srt_time(cue.start_ticks)} --> "
                f"{format_srt_time(cue.end_ticks, is_end=True, start_ticks=cue.start_ticks)}"
            )
            if cue.settings:
                timing += f" {cue.settings}"
            lines.append(timing)
            lines.extend(cue.text_lines)
            lines.append("")
        text = self.newline.join(lines)
        include_bom = self.bom if bom is None else bom
        return ("\ufeff" if include_bom else "") + text

    def to_bytes(self, *, bom: bool | None = None) -> bytes:
        return self.serialize(bom=bom).encode("utf-8")


_SRT_TIME_RE = re.compile(
    r"^(?P<hours>\d+):(?P<minutes>[0-5]\d):(?P<seconds>[0-5]\d)[,.](?P<millis>\d{3})$"
)
_TIMING_RE = re.compile(r"^(?P<start>\S+)\s+-->\s+(?P<end>\S+)(?:\s+(?P<settings>.*))?$")


def parse_srt_time(value: str) -> int:
    match = _SRT_TIME_RE.fullmatch(value.strip())
    if match is None:
        raise SrtParseError(f"invalid SRT timestamp: {value!r}")
    milliseconds = (
        int(match.group("hours")) * 3_600_000
        + int(match.group("minutes")) * 60_000
        + int(match.group("seconds")) * 1_000
        + int(match.group("millis"))
    )
    return milliseconds * TICKS_PER_MILLISECOND


def format_srt_time(ticks: int, *, is_end: bool = False, start_ticks: int | None = None) -> str:
    if ticks < 0:
        raise ValueError("SRT timestamps cannot be negative")
    milliseconds = -(-ticks // TICKS_PER_MILLISECOND) if is_end else ticks // TICKS_PER_MILLISECOND
    if is_end and start_ticks is not None:
        milliseconds = max(milliseconds, start_ticks // TICKS_PER_MILLISECOND + 1)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def parse_srt(text: str) -> SrtDocument:
    bom = text.startswith("\ufeff")
    if bom:
        text = text[1:]
    newline = "\r\n" if "\r\n" in text else "\n"
    blocks = re.split(r"(?:\r?\n){2,}", text.strip()) if text.strip() else []
    cues: list[SrtCue] = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 2:
            raise SrtParseError("SRT cue must contain an index and timing line")
        timing_match = _TIMING_RE.fullmatch(lines[1].strip())
        if timing_match is None:
            raise SrtParseError(f"invalid SRT timing line: {lines[1]!r}")
        start = parse_srt_time(timing_match.group("start"))
        end = parse_srt_time(timing_match.group("end"))
        if end < start:
            raise SrtParseError("SRT cue end precedes start")
        cues.append(
            SrtCue(
                lines[0],
                start,
                end,
                tuple(lines[2:]),
                timing_match.group("settings") or "",
            )
        )
    return SrtDocument(tuple(cues), newline, bom)
