"""Subtitle parsing and transformation primitives."""

from .ass_document import AssDocument, AssEvent, AssParseError, AssStyle, parse_ass
from .loader import LoadedTextSubtitle, SubtitleFormat, load_text_subtitle
from .srt_document import SrtCue, SrtDocument, SrtParseError, parse_srt
from .text_adapter import TextSubtitleInfo, analyze_text_subtitle

__all__ = [
    "AssDocument",
    "AssEvent",
    "AssParseError",
    "AssStyle",
    "LoadedTextSubtitle",
    "SrtCue",
    "SrtDocument",
    "SrtParseError",
    "SubtitleFormat",
    "TextSubtitleInfo",
    "analyze_text_subtitle",
    "load_text_subtitle",
    "parse_ass",
    "parse_srt",
]
