from pathlib import Path

from bdsubmerge.bdmv.timeline import RawPlaylistMark, RawPlayItem, build_playlist


def _references(tmp_path: Path, *clip_ids: str) -> tuple[Path, Path]:
    stream = tmp_path / "STREAM"
    clipinf = tmp_path / "CLIPINF"
    stream.mkdir()
    clipinf.mkdir()
    for clip_id in clip_ids:
        (stream / f"{clip_id}.m2ts").touch()
        (clipinf / f"{clip_id}.clpi").touch()
    return stream, clipinf


def test_multi_item_partial_clip_timeline_and_nonzero_in_mark(tmp_path: Path) -> None:
    stream, clipinf = _references(tmp_path, "00001", "00002")
    playlist = build_playlist(
        tmp_path / "00000.mpls",
        (
            RawPlayItem("00001", "M2TS", 45_000, 90_000),
            RawPlayItem("00002", "M2TS", 90_000, 225_000),
        ),
        (RawPlaylistMark(1, 1, 112_500),),
        stream_path=stream,
        clipinf_path=clipinf,
    )
    assert [item.logical_start_90k for item in playlist.play_items] == [0, 90_000]
    assert playlist.duration_90k == 360_000
    assert playlist.marks[0].time_90k == 135_000
    assert playlist.errors == ()


def test_chapter_at_play_item_out_boundary_is_valid(tmp_path: Path) -> None:
    stream, clipinf = _references(tmp_path, "00001")
    playlist = build_playlist(
        tmp_path / "00000.mpls",
        (RawPlayItem("00001", "M2TS", 10, 20),),
        (RawPlaylistMark(1, 0, 20),),
        stream_path=stream,
        clipinf_path=clipinf,
    )
    assert playlist.marks[0].time_90k == playlist.duration_90k
    assert playlist.errors == ()


def test_duplicate_clip_and_marks_are_reported(tmp_path: Path) -> None:
    stream, clipinf = _references(tmp_path, "00001")
    playlist = build_playlist(
        tmp_path / "00000.mpls",
        (
            RawPlayItem("00001", "M2TS", 0, 10),
            RawPlayItem("00001", "M2TS", 0, 10),
        ),
        (RawPlaylistMark(1, 0, 5), RawPlaylistMark(1, 0, 5)),
        stream_path=stream,
        clipinf_path=clipinf,
    )
    assert playlist.unique_clip_count == 1
    assert playlist.repeated_clip_count == 1
    assert any("duplicates" in warning for warning in playlist.warnings)


def test_invalid_marks_and_missing_references_do_not_abort_timeline(tmp_path: Path) -> None:
    stream, clipinf = _references(tmp_path)
    playlist = build_playlist(
        tmp_path / "00000.mpls",
        (RawPlayItem("missing", "M2TS", 100, 200),),
        (
            RawPlaylistMark(1, 2, 100),
            RawPlaylistMark(1, 0, 99),
            RawPlaylistMark(1, 0, 201),
        ),
        stream_path=stream,
        clipinf_path=clipinf,
    )
    assert len(playlist.errors) == 3
    assert not playlist.references_complete
    assert all(mark.time_90k is None for mark in playlist.marks)


def test_multi_angle_is_explicit_and_warned(tmp_path: Path) -> None:
    stream, clipinf = _references(tmp_path, "00001")
    playlist = build_playlist(
        tmp_path / "00000.mpls",
        (
            RawPlayItem(
                "00001",
                "M2TS",
                0,
                10,
                is_multi_angle=True,
                selected_angle=1,
                angle_count=2,
            ),
        ),
        (),
        stream_path=stream,
        clipinf_path=clipinf,
    )
    assert playlist.play_items[0].selected_angle == 1
    assert playlist.has_multi_angle
    assert any("multi-angle" in warning for warning in playlist.warnings)


def test_twenty_four_episode_accumulation_has_no_drift(tmp_path: Path) -> None:
    stream, clipinf = _references(tmp_path, *(f"{index:05}" for index in range(24)))
    duration_45k = 1_234_567
    playlist = build_playlist(
        tmp_path / "00000.mpls",
        tuple(
            RawPlayItem(f"{index:05}", "M2TS", 77, 77 + duration_45k)
            for index in range(24)
        ),
        (),
        stream_path=stream,
        clipinf_path=clipinf,
    )
    assert playlist.duration_90k == duration_45k * 2 * 24
    assert playlist.play_items[-1].logical_end_90k == duration_45k * 2 * 24
