"""Text subtitle loading independent of paths and user interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .ass_document import AssDocument, parse_ass
from .encoding import DecodedText, decode_subtitle
from .srt_document import SrtDocument, parse_srt


class SubtitleFormat(Enum):
    ASS = "ass"
    SSA = "ssa"
    SRT = "srt"
    SUP = "sup"


class UnsupportedSubtitleFormatError(ValueError):
    """Raised when a text subtitle format cannot be established safely."""


@dataclass(frozen=True, slots=True)
class LoadedTextSubtitle:
    format: SubtitleFormat
    document: AssDocument | SrtDocument
    encoding: str
    bom: bool


def format_from_name(name: str) -> SubtitleFormat:
    suffix = name.rsplit(".", 1)[-1].casefold() if "." in name else ""
    try:
        return SubtitleFormat(suffix)
    except ValueError as error:
        raise UnsupportedSubtitleFormatError(f"unsupported subtitle extension: {name!r}") from error


def load_text_subtitle(
    data: bytes,
    *,
    name: str,
    encoding: str | None = None,
) -> LoadedTextSubtitle:
    subtitle_format = format_from_name(name)
    if subtitle_format is SubtitleFormat.SUP:
        raise UnsupportedSubtitleFormatError("SUP is a binary PGS format")
    decoded: DecodedText = decode_subtitle(data, encoding=encoding)
    if subtitle_format in {SubtitleFormat.ASS, SubtitleFormat.SSA}:
        document: AssDocument | SrtDocument = parse_ass(decoded.text)
    else:
        document = parse_srt(decoded.text)
    return LoadedTextSubtitle(subtitle_format, document, decoded.encoding, decoded.bom)
