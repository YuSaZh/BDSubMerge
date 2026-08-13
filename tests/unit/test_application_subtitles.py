from pathlib import Path

from bdsubmerge.application import (
    ImportSubtitlesRequest,
    LoadSubtitlesRequest,
    SubtitleApplicationService,
    SubtitleInput,
)
from bdsubmerge.cancellation import progress_scope
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


def test_discover_and_load_preserves_existing_order_and_reports_current_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Subtitles"
    root.mkdir()
    episode_1 = root / "E1.ass"
    episode_2 = root / "E2.ass"
    episode_10 = root / "E10.ass"
    for path in (episode_1, episode_2, episode_10):
        path.write_bytes(ASS)
    progress: list[tuple[int, str]] = []
    service = SubtitleApplicationService()

    with progress_scope(lambda value, detail: progress.append((value, detail))):
        result = service.discover_and_load(
            ImportSubtitlesRequest((episode_10, episode_1), (root,))
        )

    assert result.changed is True
    assert result.paths == (episode_10, episode_1, episode_2)
    assert result.subtitles is not None
    assert tuple(asset.path for asset in result.subtitles.assets) == result.paths
    assert result.input_directories == (root,)
    assert any(detail == str(episode_2) for _, detail in progress)


def test_discover_and_load_does_not_reload_duplicate_inputs(tmp_path: Path) -> None:
    root = tmp_path / "Subtitles"
    root.mkdir()
    episode = root / "E1.ass"
    episode.write_bytes(ASS)
    service = SubtitleApplicationService()

    result = service.discover_and_load(
        ImportSubtitlesRequest((episode,), (root,))
    )

    assert result.changed is False
    assert result.found_subtitles is True
    assert result.subtitles is None


def test_discover_and_load_returns_bdmv_file_as_scan_candidate(tmp_path: Path) -> None:
    index_bdmv = tmp_path / "BDMV" / "index.bdmv"
    index_bdmv.parent.mkdir()
    index_bdmv.write_bytes(b"index")

    result = SubtitleApplicationService().discover_and_load(
        ImportSubtitlesRequest((), (index_bdmv,))
    )

    assert result.changed is False
    assert result.found_subtitles is False
    assert result.scan_candidate == index_bdmv
