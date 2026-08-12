"""Subtitle parsing and transformation primitives."""

from .ass_document import AssDocument, AssEvent, AssParseError, AssStyle, parse_ass
from .loader import LoadedTextSubtitle, SubtitleFormat, load_text_subtitle
from .pgs_adapter import (
    PgsDocument,
    PgsDurationInfo,
    PgsPacket,
    PgsParseError,
    PgsSegmentType,
    PgsSource,
    PgsTimestampOverflowError,
    TimestampOverflowPolicy,
    append_sup_sources,
    estimate_sup_duration,
    parse_sup,
    shift_sup,
)
from .srt_document import SrtCue, SrtDocument, SrtParseError, parse_srt
from .text_adapter import TextSubtitleInfo, analyze_text_subtitle

__all__ = [
    "AssDocument",
    "AssEvent",
    "AssParseError",
    "AssStyle",
    "LoadedTextSubtitle",
    "PgsDocument",
    "PgsDurationInfo",
    "PgsPacket",
    "PgsParseError",
    "PgsSegmentType",
    "PgsSource",
    "PgsTimestampOverflowError",
    "SrtCue",
    "SrtDocument",
    "SrtParseError",
    "SubtitleFormat",
    "TextSubtitleInfo",
    "TimestampOverflowPolicy",
    "analyze_text_subtitle",
    "append_sup_sources",
    "estimate_sup_duration",
    "load_text_subtitle",
    "parse_ass",
    "parse_srt",
    "parse_sup",
    "shift_sup",
]
