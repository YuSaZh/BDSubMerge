import pytest

from bdsubmerge.subtitles.encoding import EncodingDetectionError
from bdsubmerge.subtitles.loader import SubtitleFormat, load_text_subtitle
from bdsubmerge.subtitles.srt_document import format_srt_time, parse_srt

SRT_TEXT = """\ufeff9\r
00:00:01,001 --> 00:00:02,002 position:50%\r
first line\r
second line\r
\r
12\r
00:00:02,100 --> 00:00:03,000\r
next\r
"""


def test_srt_preserves_text_and_settings_but_renumbers() -> None:
    document = parse_srt(SRT_TEXT)

    assert document.bom is True
    assert document.cues[0].text_lines == ("first line", "second line")
    assert document.cues[0].settings == "position:50%"
    serialized = document.serialize()
    assert serialized.startswith("\ufeff1\r\n")
    assert "2\r\n00:00:02,100 --> 00:00:03,000" in serialized


def test_srt_time_uses_integer_ticks_and_outward_rounding() -> None:
    document = parse_srt(SRT_TEXT)

    assert document.cues[0].start_ticks == 90_090
    assert format_srt_time(89) == "00:00:00,000"
    assert format_srt_time(89, is_end=True) == "00:00:00,001"


def test_loader_detects_utf8_bom_and_format() -> None:
    loaded = load_text_subtitle(SRT_TEXT.encode("utf-8"), name="episode.SRT")

    assert loaded.format is SubtitleFormat.SRT
    assert loaded.bom is True
    assert loaded.encoding == "utf-8-sig"


@pytest.mark.parametrize(
    ("marker", "codec"),
    ((b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")),
)
def test_loader_detects_utf16_bom_and_decodes_chinese_text(marker: bytes, codec: str) -> None:
    text = "1\r\n00:00:00,000 --> 00:00:01,000\r\n中文字幕\r\n"

    loaded = load_text_subtitle(marker + text.encode(codec), name="episode.srt")

    assert loaded.encoding == codec
    assert loaded.bom is True
    assert loaded.document.cues[0].text_lines == ("中文字幕",)


def test_loader_requires_explicit_gb18030_choice_before_decoding() -> None:
    text = "1\r\n00:00:00,000 --> 00:00:01,000\r\n简体中文字幕\r\n"
    data = text.encode("gb18030")

    with pytest.raises(EncodingDetectionError, match="explicitly choose gb18030"):
        load_text_subtitle(data, name="episode.srt")

    loaded = load_text_subtitle(data, name="episode.srt", encoding="gb18030")

    assert loaded.encoding == "gb18030"
    assert loaded.bom is False
    assert loaded.document.cues[0].text_lines == ("简体中文字幕",)
