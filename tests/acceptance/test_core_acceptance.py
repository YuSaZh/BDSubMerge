from dataclasses import replace
from pathlib import Path

from bdsubmerge.application import (
    ExecuteMergeRequest,
    LoadSubtitlesRequest,
    MergeApplicationService,
    PrepareMergeRequest,
    SubtitleApplicationService,
    SubtitleInput,
)
from bdsubmerge.domain.models import (
    BdmvLayout,
    PlayItemInfo,
    PlaylistInfo,
    ReferenceStatus,
)
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.merge import MergePlan, MergeSource, merge_ass
from bdsubmerge.output import FullPathOutputTarget
from bdsubmerge.subtitles.ass_document import format_ass_time, parse_ass, parse_ass_time
from bdsubmerge.subtitles.srt_document import format_srt_time, parse_srt_time

SECOND = 90_000
ASS_EPISODE = (
    b"[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
    b"[V4+ Styles]\nFormat: Name\nStyle: Default\n"
    b"[Events]\nFormat: Start, End, Style, Text\n"
    b"Dialogue: 0:00:00.00,0:23:50.00,Default,line\n"
)


def _layout(tmp_path: Path) -> BdmvLayout:
    bdmv = tmp_path / "Title" / "BDMV"
    playlist_path = bdmv / "PLAYLIST"
    playlist_path.mkdir(parents=True)
    (bdmv / "CLIPINF").mkdir()
    (bdmv / "STREAM").mkdir()
    index = bdmv / "index.bdmv"
    index.write_bytes(b"immutable index")
    return BdmvLayout(
        selected_path=tmp_path / "Title",
        disc_container_path=tmp_path / "Title",
        bdmv_path=bdmv,
        index_bdmv_path=index,
        playlist_path=playlist_path,
        clipinf_path=bdmv / "CLIPINF",
        stream_path=bdmv / "STREAM",
    )


def _playlist(layout: BdmvLayout, *, count: int = 24) -> PlaylistInfo:
    duration = 24 * 60 * SECOND
    items = tuple(
        PlayItemInfo(
            index=index,
            clip_id=f"{index + 1:05d}",
            codec_id="M2TS",
            in_time_45k=0,
            out_time_45k=duration // 2,
            logical_start_90k=MediaTick90k(index * duration),
            logical_end_90k=MediaTick90k((index + 1) * duration),
            connection_condition=1,
            is_multi_angle=False,
            selected_angle=0,
            angle_count=1,
            references=ReferenceStatus(True, True),
        )
        for index in range(count)
    )
    path = layout.playlist_path / "00001.mpls"
    path.write_bytes(b"immutable playlist")
    return PlaylistInfo(
        path=path,
        stem="00001",
        duration_90k=MediaTick90k(count * duration),
        play_items=items,
        marks=(),
    )


def _source_metadata(paths: tuple[Path, ...]) -> tuple[tuple[Path, int, int], ...]:
    return tuple((path, path.stat().st_size, path.stat().st_mtime_ns) for path in paths)


def test_ac03_merge_does_not_modify_bdmv_sources(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout, count=1)
    clip = layout.stream_path / "00001.m2ts"
    clip_info = layout.clipinf_path / "00001.clpi"
    clip.write_bytes(b"immutable media")
    clip_info.write_bytes(b"immutable clip metadata")
    subtitle = tmp_path / "episode.ass"
    subtitle.write_bytes(ASS_EPISODE)
    sources = (layout.index_bdmv_path, playlist.path, clip_info, clip)
    before = _source_metadata(sources)
    loaded = SubtitleApplicationService().load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle),))
    )

    service = MergeApplicationService()
    prepared = service.prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            loaded,
            (FullPathOutputTarget("output", path=tmp_path / "out.ass"),),
            accept_low_confidence=True,
        )
    )

    executed = service.execute(ExecuteMergeRequest(prepared))

    assert prepared.ready is True
    assert executed.succeeded is True
    assert executed.receipt is not None
    assert (tmp_path / "out.ass").is_file()
    assert _source_metadata(sources) == before


def test_ac04_twenty_four_episode_mapping_has_no_cumulative_drift(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout)
    subtitle_paths = tuple(tmp_path / f"E{index + 1:02d}.ass" for index in range(24))
    for path in subtitle_paths:
        path.write_bytes(ASS_EPISODE)
    loaded = SubtitleApplicationService().load_ordered(
        LoadSubtitlesRequest(tuple(SubtitleInput(path) for path in subtitle_paths))
    )

    prepared = MergeApplicationService().prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            loaded,
            (FullPathOutputTarget("output", path=tmp_path / "out.ass"),),
            accept_low_confidence=True,
        )
    )

    assert prepared.mapping is not None
    duration = 24 * 60 * SECOND
    assert [int(item.start_boundary.time_90k) for item in prepared.mapping.mappings] == [
        index * duration for index in range(24)
    ]
    assert [int(item.final_offset_90k) for item in prepared.mapping.mappings] == [
        index * duration for index in range(24)
    ]
    assert isinstance(prepared.payload, str)
    output = parse_ass(prepared.payload)
    assert [event.start_ticks for event in output.events] == [
        index * duration for index in range(24)
    ]


def test_ac04_ass_and_srt_serialization_stay_within_format_precision() -> None:
    tick = 24 * 60 * SECOND + 899

    ass_start = parse_ass_time(format_ass_time(tick))
    ass_end = parse_ass_time(format_ass_time(tick, is_end=True))
    srt_start = parse_srt_time(format_srt_time(tick))
    srt_end = parse_srt_time(format_srt_time(tick, is_end=True))

    assert 0 <= tick - ass_start < 900
    assert 0 <= ass_end - tick < 900
    assert 0 <= tick - srt_start < 90
    assert 0 <= srt_end - tick < 90


def test_ac05_ass_style_conflict_rewrites_only_style_references() -> None:
    first = parse_ass(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
        "[V4+ Styles]\nFormat: Name, Fontname, PrimaryColour\n"
        "Style: Default,Arial,&H00FFFFFF\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,first\n"
    )
    second = parse_ass(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
        "[V4+ Styles]\nFormat: Name, Fontname, PrimaryColour\n"
        "Style: Default,Arial,&H0000FFFF\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        r"Dialogue: 0:00:00.00,0:00:01.00,Default,{\bord2\rDefault\c&HFF0000&}second"
        "\n"
    )

    result = merge_ass(
        MergePlan((MergeSource("E01", first, 0), MergeSource("E02", second, SECOND)))
    )

    assert [style.name for style in result.document.styles] == ["Default", "Default__E02"]
    event = result.document.events[1]
    assert event.value("Style") == "Default__E02"
    assert event.value("Text") == r"{\bord2\rDefault__E02\c&HFF0000&}second"


def test_ac08_low_confidence_requires_explicit_confirmation(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout, count=1)
    subtitle = tmp_path / "short.ass"
    subtitle.write_bytes(ASS_EPISODE.replace(b"0:23:50.00", b"0:00:10.00"))
    loaded = SubtitleApplicationService().load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle),))
    )
    request = PrepareMergeRequest(
        layout,
        playlist,
        loaded,
        (FullPathOutputTarget("output", path=tmp_path / "out.ass"),),
    )

    blocked = MergeApplicationService().prepare(request)

    assert blocked.mapping is not None
    assert blocked.mapping.has_low_confidence is True
    assert blocked.ready is False
    assert "low_mapping_confidence" in {issue.code for issue in blocked.issues}

    accepted = MergeApplicationService().prepare(
        replace(request, accept_low_confidence=True)
    )

    assert accepted.ready is True
