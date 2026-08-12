"""Conservative subtitle text encoding detection."""

from __future__ import annotations

from dataclasses import dataclass


class EncodingDetectionError(UnicodeError):
    """Raised when byte input cannot be decoded without an unsafe guess."""


@dataclass(frozen=True, slots=True)
class DecodedText:
    text: str
    encoding: str
    bom: bool
    confident: bool


_BOMS: tuple[tuple[bytes, str], ...] = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)


def decode_subtitle(data: bytes, *, encoding: str | None = None) -> DecodedText:
    """Decode known Unicode safely; require a choice for ambiguous legacy bytes."""

    if encoding is not None:
        normalized = encoding.casefold().replace("_", "-")
        bom = any(data.startswith(marker) for marker, _ in _BOMS)
        text = data.decode(encoding)
        if normalized == "utf-8-sig":
            text = text.removeprefix("\ufeff")
        elif normalized in {"utf-16", "utf-16-le", "utf-16-be"}:
            text = text.removeprefix("\ufeff")
        return DecodedText(text, encoding, bom, True)
    for marker, detected in _BOMS:
        if data.startswith(marker):
            payload = data[len(marker) :]
            codec = "utf-8" if detected == "utf-8-sig" else detected
            return DecodedText(payload.decode(codec), detected, True, True)
    try:
        return DecodedText(data.decode("utf-8"), "utf-8", False, True)
    except UnicodeDecodeError as error:
        raise EncodingDetectionError(
            "legacy subtitle encoding is ambiguous; explicitly choose gb18030 or shift_jis"
        ) from error
