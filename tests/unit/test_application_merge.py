import json
from dataclasses import replace
from pathlib import Path

import pytest

from bdsubmerge.application import (
    ExecuteMergeRequest,
    LoadSubtitlesRequest,
    MergeApplicationService,
    MergeReportFormat,
    MergeReportTarget,
    PrepareMergeRequest,
    SubtitleApplicationService,
    SubtitleInput,
    build_playlist_boundaries,
)
from bdsubmerge.domain.models import (
    BdmvLayout,
    PlayItemInfo,
    PlaylistInfo,
    PlaylistMarkInfo,
    ReferenceStatus,
    SourceFingerprint,
)
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.mapping import (
    BoundaryKind,
    BoundarySource,
    MappingLock,
    boundary,
)
from bdsubmerge.output import CollisionPolicy, FullPathOutputTarget

ASS = (
    b"[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
    b"[V4+ Styles]\nFormat: Name\nStyle: Default\n"
    b"[Events]\nFormat: Start, End, Style, Text\n"
    b"Dialogue: 0:00:00.00,0:01:00.00,Default,line\n"
)


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


SUP = _pg_packet(60 * 90_000, 60 * 90_000 - 10, 0x16, b"pcs") + _pg_packet(
    60 * 90_000,
    60 * 90_000,
    0x80,
)


def _layout(tmp_path: Path) -> BdmvLayout:
    bdmv = tmp_path / "Title" / "BDMV"
    playlist_path = bdmv / "PLAYLIST"
    playlist_path.mkdir(parents=True)
    (bdmv / "CLIPINF").mkdir()
    (bdmv / "STREAM").mkdir()
    index = bdmv / "index.bdmv"
    index.write_bytes(b"index")
    return BdmvLayout(
        selected_path=tmp_path / "Title",
        disc_container_path=tmp_path / "Title",
        bdmv_path=bdmv,
        index_bdmv_path=index,
        playlist_path=playlist_path,
        clipinf_path=bdmv / "CLIPINF",
        stream_path=bdmv / "STREAM",
    )


def _playlist(layout: BdmvLayout) -> PlaylistInfo:
    mpls = layout.playlist_path / "00001.mpls"
    mpls.write_bytes(b"mpls")
    item = PlayItemInfo(
        index=0,
        clip_id="00001",
        codec_id="M2TS",
        in_time_45k=0,
        out_time_45k=2_700_000,
        logical_start_90k=MediaTick90k(0),
        logical_end_90k=MediaTick90k(60 * 90_000),
        connection_condition=1,
        is_multi_angle=False,
        selected_angle=0,
        angle_count=1,
        references=ReferenceStatus(True, True),
    )
    return PlaylistInfo(
        path=mpls,
        stem="00001",
        duration_90k=MediaTick90k(60 * 90_000),
        play_items=(item,),
        marks=(PlaylistMarkInfo(0, 1, 0, 0, MediaTick90k(0)),),
    )


def _source_fingerprint(path: Path) -> SourceFingerprint:
    stat = path.stat()
    return SourceFingerprint(stat.st_size, stat.st_mtime_ns)


def _capture_bdmv_fingerprints(
    layout: BdmvLayout,
    playlist: PlaylistInfo,
) -> tuple[BdmvLayout, PlaylistInfo]:
    return (
        replace(
            layout,
            index_fingerprint=_source_fingerprint(layout.index_bdmv_path),
        ),
        replace(
            playlist,
            source_fingerprint=_source_fingerprint(playlist.path),
        ),
    )


def test_boundary_builder_retains_playlist_item_and_chapter_sources(tmp_path: Path) -> None:
    playlist = _playlist(_layout(tmp_path))

    boundaries = build_playlist_boundaries(playlist)

    assert len(boundaries) == 2
    assert boundaries[0].kinds == {
        BoundaryKind.PLAYLIST_START,
        BoundaryKind.PLAY_ITEM_START,
        BoundaryKind.CHAPTER,
    }
    assert boundaries[1].kinds == {
        BoundaryKind.PLAYLIST_END,
        BoundaryKind.PLAY_ITEM_END,
    }


def test_prepare_merges_and_dry_run_never_writes(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout)
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(ASS)
    loader = SubtitleApplicationService(read_bytes=lambda path: ASS)
    subtitles = loader.load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    destination = tmp_path / "output.ass"
    service = MergeApplicationService()

    prepared = service.prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("output", path=destination),),
        )
    )
    result = service.execute(ExecuteMergeRequest(prepared, dry_run=True))

    assert prepared.ready is True
    assert prepared.mapping is not None
    assert prepared.report is not None
    assert result.succeeded is True
    assert result.receipt is None
    assert not destination.exists()


def test_low_confidence_or_invalid_output_blocks_execution(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout)
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(ASS)
    subtitles = SubtitleApplicationService(read_bytes=lambda path: ASS).load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    existing = tmp_path / "output.ass"
    existing.write_text("existing", encoding="utf-8")
    service = MergeApplicationService()

    prepared = service.prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("output", path=existing),),
            accept_low_confidence=True,
        )
    )
    result = service.execute(ExecuteMergeRequest(prepared))

    assert prepared.ready is False
    assert "output_destination_exists" in {issue.code for issue in prepared.issues}
    assert result.succeeded is False
    assert existing.read_text(encoding="utf-8") == "existing"


def test_sup_uses_shared_prepare_dry_run_and_atomic_write_flow(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout)
    subtitle_path = tmp_path / "episode.sup"
    subtitle_path.write_bytes(SUP)
    subtitles = SubtitleApplicationService(read_bytes=lambda path: SUP).load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    destination = tmp_path / "output.sup"
    service = MergeApplicationService()
    prepared = service.prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("output", path=destination),),
            accept_low_confidence=True,
        )
    )

    dry_run = service.execute(ExecuteMergeRequest(prepared, dry_run=True))

    assert prepared.ready is True
    assert prepared.payload == SUP
    assert dry_run.succeeded is True
    assert not destination.exists()

    written = service.execute(ExecuteMergeRequest(prepared))

    assert written.succeeded is True
    assert destination.read_bytes() == SUP


def test_missing_source_blocks_merge_before_output(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout)
    subtitle_path = tmp_path / "missing.ass"
    subtitles = SubtitleApplicationService(read_bytes=lambda path: ASS).load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )

    prepared = MergeApplicationService().prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("output", path=tmp_path / "output.ass"),),
        )
    )

    assert prepared.ready is False
    assert "missing_subtitle_source" in {issue.code for issue in prepared.issues}


@pytest.mark.parametrize("source_name", ("index", "playlist", "subtitle"))
@pytest.mark.parametrize("change", ("changed", "missing"))
def test_prepare_blocks_source_changed_or_missing_since_load(
    tmp_path: Path,
    source_name: str,
    change: str,
) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout)
    layout, playlist = _capture_bdmv_fingerprints(layout, playlist)
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(ASS)
    subtitles = SubtitleApplicationService().load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    source_path = {
        "index": layout.index_bdmv_path,
        "playlist": playlist.path,
        "subtitle": subtitle_path,
    }[source_name]
    if change == "changed":
        source_path.write_bytes(source_path.read_bytes() + b"changed")
    else:
        source_path.unlink()

    prepared = MergeApplicationService().prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("output", path=tmp_path / "output.ass"),),
        )
    )

    assert prepared.ready is False
    assert f"source_{change}_since_load" in {issue.code for issue in prepared.issues}


@pytest.mark.parametrize("source_name", ("index", "playlist", "subtitle"))
def test_execute_rechecks_sources_before_writing(
    tmp_path: Path,
    source_name: str,
) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout)
    layout, playlist = _capture_bdmv_fingerprints(layout, playlist)
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(ASS)
    subtitles = SubtitleApplicationService().load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    destination = tmp_path / "output.ass"
    service = MergeApplicationService()
    prepared = service.prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("output", path=destination),),
        )
    )
    source_path = {
        "index": layout.index_bdmv_path,
        "playlist": playlist.path,
        "subtitle": subtitle_path,
    }[source_name]
    source_path.write_bytes(source_path.read_bytes() + b"changed after preflight")

    result = service.execute(ExecuteMergeRequest(prepared))

    assert prepared.ready is True
    assert result.succeeded is False
    assert {issue.code for issue in result.issues} == {"source_changed_since_load"}
    assert destination.exists() is False


def test_additional_user_boundary_changes_automatic_mapping(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = replace(
        _playlist(layout),
        duration_90k=MediaTick90k(120 * 90_000),
        play_items=(),
        marks=(),
    )
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(ASS)
    subtitles = SubtitleApplicationService(read_bytes=lambda path: ASS).load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    user_boundary = boundary(
        "user:1",
        60 * 90_000,
        BoundarySource(BoundaryKind.USER, "ui"),
        user_created=True,
    )
    service = MergeApplicationService()

    automatic = service.prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("automatic", path=tmp_path / "automatic.ass"),),
            accept_low_confidence=True,
        )
    )
    with_user_boundary = service.prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("user", path=tmp_path / "user.ass"),),
            additional_boundaries=(user_boundary,),
            accept_low_confidence=True,
        )
    )

    assert automatic.mapping is not None
    assert with_user_boundary.mapping is not None
    assert (
        int(automatic.mapping.mappings[0].interval_duration_90k) == 120 * 90_000
    )
    assert (
        int(with_user_boundary.mapping.mappings[0].interval_duration_90k) == 60 * 90_000
    )
    assert with_user_boundary.mapping.mappings[0].end_boundary.id == "user:1"


def test_restored_lock_can_reference_additional_user_boundary(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = replace(
        _playlist(layout),
        duration_90k=MediaTick90k(120 * 90_000),
        play_items=(),
        marks=(),
    )
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(ASS)
    subtitles = SubtitleApplicationService(read_bytes=lambda path: ASS).load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    user_boundary = boundary(
        "user:restored",
        60 * 90_000,
        BoundarySource(BoundaryKind.USER, "ui"),
        user_created=True,
    )

    prepared = MergeApplicationService().prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("output", path=tmp_path / "output.ass"),),
            locks=(
                MappingLock(
                    "episode-1",
                    "playlist:start",
                    "user:restored",
                    MediaTick90k(900),
                ),
            ),
            additional_boundaries=(user_boundary,),
            accept_low_confidence=True,
        )
    )

    assert prepared.mapping is not None
    mapping = prepared.mapping.mappings[0]
    assert mapping.locked is True
    assert mapping.start_boundary.id == "playlist:start"
    assert mapping.end_boundary.id == "user:restored"
    assert mapping.manual_offset_90k == 900


def test_restored_user_lock_survives_coincident_boundary_normalization(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    playlist = replace(
        _playlist(layout),
        duration_90k=MediaTick90k(120 * 90_000),
        play_items=(),
        marks=(),
    )
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(ASS)
    subtitles = SubtitleApplicationService(read_bytes=lambda path: ASS).load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    user_start = boundary(
        "user:start",
        0,
        BoundarySource(BoundaryKind.USER, "ui"),
        user_created=True,
    )

    prepared = MergeApplicationService().prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("output", path=tmp_path / "output.ass"),),
            locks=(MappingLock("episode-1", "user:start", "playlist:end"),),
            additional_boundaries=(user_start,),
            accept_low_confidence=True,
        )
    )

    assert prepared.mapping is not None
    mapping = prepared.mapping.mappings[0]
    assert mapping.locked is True
    assert mapping.start_boundary.time_90k == 0
    assert BoundaryKind.USER in mapping.start_boundary.kinds


def test_invalid_additional_boundary_returns_mapping_failed(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout)
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(ASS)
    subtitles = SubtitleApplicationService(read_bytes=lambda path: ASS).load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    invalid_boundaries = (
        boundary(
            "chapter:extra",
            30 * 90_000,
            BoundarySource(BoundaryKind.CHAPTER, "ui"),
        ),
        boundary(
            "user:outside",
            61 * 90_000,
            BoundarySource(BoundaryKind.USER, "ui"),
            user_created=True,
        ),
    )

    for invalid_boundary in invalid_boundaries:
        prepared = MergeApplicationService().prepare(
            PrepareMergeRequest(
                layout,
                playlist,
                subtitles,
                (FullPathOutputTarget("output", path=tmp_path / "output.ass"),),
                additional_boundaries=(invalid_boundary,),
            )
        )

        assert prepared.mapping is None
        assert {issue.code for issue in prepared.issues} == {"mapping_failed"}


@pytest.mark.parametrize(
    ("report_format", "extension"),
    ((MergeReportFormat.JSON, "json"), (MergeReportFormat.TEXT, "txt")),
)
def test_optional_report_is_written_with_subtitle_in_one_transaction(
    tmp_path: Path,
    report_format: MergeReportFormat,
    extension: str,
) -> None:
    private_body = "private subtitle body must not enter reports"
    subtitle_data = ASS.replace(b",Default,line", f",Default,{private_body}".encode())
    layout = _layout(tmp_path)
    playlist = _playlist(layout)
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(subtitle_data)
    subtitles = SubtitleApplicationService(read_bytes=lambda path: subtitle_data).load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    destination = tmp_path / "output.ass"
    report_path = tmp_path / f"merge-report.{extension}"
    service = MergeApplicationService()

    prepared = service.prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("output", path=destination),),
            report_target=MergeReportTarget(report_path, report_format),
        )
    )
    result = service.execute(ExecuteMergeRequest(prepared))

    assert prepared.ready is True
    assert prepared.execution_report is not None
    assert prepared.report_payload is not None
    assert private_body not in prepared.report_payload
    assert result.succeeded is True
    assert result.receipt is not None
    assert result.receipt.paths == (destination, report_path)
    assert private_body in destination.read_text(encoding="utf-8-sig")
    if report_format is MergeReportFormat.JSON:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert payload["playlist"]["stem"] == "00001"
        assert payload["play_items"][0]["logical_end_90k"] == 60 * 90_000
        assert payload["episodes"][0]["effective_end_90k"] == 60 * 90_000
        assert payload["output_paths"] == [str(destination)]
        assert len(payload["source_fingerprints"]) == 3
    else:
        report_text = report_path.read_text(encoding="utf-8")
        assert "PlayItem timeline" in report_text
        assert "logical_90k=0..5400000" in report_text
        assert f"report: {report_path}" in report_text


def test_report_commit_failure_leaves_subtitle_output_unwritten(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout)
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(ASS)
    subtitles = SubtitleApplicationService(read_bytes=lambda path: ASS).load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    destination = tmp_path / "output.ass"
    report_path = tmp_path / "merge-report.json"
    service = MergeApplicationService()
    prepared = service.prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("output", path=destination),),
            report_target=MergeReportTarget(report_path, MergeReportFormat.JSON),
        )
    )
    report_path.write_text("appeared after preflight", encoding="utf-8")

    result = service.execute(ExecuteMergeRequest(prepared))

    assert prepared.ready is True
    assert result.succeeded is False
    assert {issue.code for issue in result.issues} == {"output_write_failed"}
    assert destination.exists() is False
    assert report_path.read_text(encoding="utf-8") == "appeared after preflight"
    assert tuple(tmp_path.glob(".*.tmp")) == ()
    assert tuple(tmp_path.glob(".*.rollback")) == ()


def test_report_target_cannot_overwrite_project_file(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    playlist = _playlist(layout)
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(ASS)
    subtitles = SubtitleApplicationService(read_bytes=lambda path: ASS).load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    project_path = tmp_path / "show.bdsm.json"
    project_path.write_text("project snapshot", encoding="utf-8")

    prepared = MergeApplicationService().prepare(
        PrepareMergeRequest(
            layout,
            playlist,
            subtitles,
            (FullPathOutputTarget("output", path=tmp_path / "output.ass"),),
            report_target=MergeReportTarget(
                project_path,
                MergeReportFormat.JSON,
                CollisionPolicy.OVERWRITE,
                (project_path,),
            ),
        )
    )

    assert prepared.ready is False
    assert "report_overwrites_input" in {issue.code for issue in prepared.issues}
    assert project_path.read_text(encoding="utf-8") == "project snapshot"
