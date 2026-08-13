"""Format-neutral projections for imported text subtitles."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from bdsubmerge.cancellation import CancellationCheck, raise_if_cancelled

from .ass_document import AssDocument
from .srt_document import SrtDocument


@dataclass(frozen=True, slots=True)
class TextSubtitleInfo:
    event_count: int
    style_count: int
    earliest_start_ticks: int | None
    raw_end_ticks: int | None
    effective_end_ticks: int | None
    suspected_long_tail: bool
    play_res_x: int | None = None
    play_res_y: int | None = None
    duration_estimated: bool = False


def _effective_end(
    ends: Sequence[int],
    long_tail_threshold_ticks: int,
) -> tuple[int | None, bool]:
    if not ends:
        return None, False
    ordered = sorted(ends)
    if len(ordered) >= 2 and ordered[-1] - ordered[-2] > long_tail_threshold_ticks:
        return ordered[-2], True
    return ordered[-1], False


def _script_info_integer(document: AssDocument, key: str) -> int | None:
    for entry in document.script_info:
        if entry.key.casefold() == key.casefold():
            try:
                return int(entry.value.strip())
            except ValueError:
                return None
    return None


def analyze_text_subtitle(
    document: AssDocument | SrtDocument,
    *,
    long_tail_threshold_ticks: int = 300 * 90_000,
    cancellation_check: CancellationCheck | None = None,
) -> TextSubtitleInfo:
    raise_if_cancelled(cancellation_check)
    if isinstance(document, AssDocument):
        events = document.events
        starts: list[int] = []
        all_ends: list[int] = []
        dialogue_ends: list[int] = []
        for event in events:
            raise_if_cancelled(cancellation_check)
            starts.append(event.start_ticks)
            all_ends.append(event.end_ticks)
            if event.kind.casefold() != "comment":
                dialogue_ends.append(event.end_ticks)
        effective_end, suspected = _effective_end(dialogue_ends, long_tail_threshold_ticks)
        return TextSubtitleInfo(
            len(events),
            len(document.styles),
            min(starts, default=None),
            max(all_ends, default=None),
            effective_end,
            suspected,
            _script_info_integer(document, "PlayResX"),
            _script_info_integer(document, "PlayResY"),
        )
    starts = []
    ends = []
    for cue in document.cues:
        raise_if_cancelled(cancellation_check)
        starts.append(cue.start_ticks)
        ends.append(cue.end_ticks)
    effective_end, suspected = _effective_end(ends, long_tail_threshold_ticks)
    return TextSubtitleInfo(
        len(document.cues),
        0,
        min(starts, default=None),
        max(ends, default=None),
        effective_end,
        suspected,
    )
