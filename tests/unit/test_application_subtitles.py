from pathlib import Path

from bdsubmerge.application import (
    LoadSubtitlesRequest,
    SubtitleApplicationService,
    SubtitleInput,
)
from bdsubmerge.subtitles import SubtitleFormat

ASS = (
    b"[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
    b"[V4+ Styles]\nFormat: Name\nStyle: Default\n"
    b"[Events]\nFormat: Start, End, Style, Text\n"
    b"Dialogue: 0:00:00.00,0:01:00.00,Default,line\n"
)
SRT = b"1\r\n00:00:00,000 --> 00:01:00,000\r\nline\r\n"


def _pg_packet(pts: int, dts: int, segment_type: int, payload: bytes = b"") -> bytes:
    return b"".join(
        (
            b"PG",
            pts.to_bytes(4, "big"),
            dts.to_bytes(4, "big"),
            bytes((segment_type,)),
            len(payload).to_bytes(2, "big"),
            payload,
        )
    )


SUP = _pg_packet(90_000, 89_990, 0x16, b"pcs") + _pg_packet(
    90_000,
    90_000,
    0x80,
)


def test_load_ordered_preserves_request_order_and_analyzes_assets() -> None:
    data = {"02.ass": ASS, "01.ass": ASS}
    service = SubtitleApplicationService(read_bytes=lambda path: data[path.name])
    request = LoadSubtitlesRequest(
        (SubtitleInput(Path("02.ass")), SubtitleInput(Path("01.ass")))
    )

    result = service.load_ordered(request)

    assert result.ready is True
    assert result.format is SubtitleFormat.ASS
    assert [asset.path.name for asset in result.assets] == ["02.ass", "01.ass"]
    assert result.assets[0].analysis.effective_end_ticks == 60 * 90_000


def test_mixed_formats_are_a_graceful_blocking_result() -> None:
    data = {"one.ass": ASS, "two.srt": SRT}
    service = SubtitleApplicationService(read_bytes=lambda path: data[path.name])

    mixed = service.load_ordered(
        LoadSubtitlesRequest(
            (SubtitleInput(Path("one.ass")), SubtitleInput(Path("two.srt")))
        )
    )
    assert mixed.ready is False
    assert "mixed_subtitle_formats" in {issue.code for issue in mixed.issues}


def test_sup_is_loaded_with_estimated_duration_warning() -> None:
    service = SubtitleApplicationService(read_bytes=lambda path: SUP)

    result = service.load_ordered(
        LoadSubtitlesRequest((SubtitleInput(Path("episode.sup")),))
    )

    assert result.ready is True
    assert result.format is SubtitleFormat.SUP
    assert result.assets[0].analysis.effective_end_ticks == 90_000
    assert result.assets[0].analysis.duration_estimated is True
    assert "sup_duration_estimated" in {issue.code for issue in result.issues}
