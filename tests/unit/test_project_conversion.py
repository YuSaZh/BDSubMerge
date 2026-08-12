from pathlib import Path

from bdsubmerge.project.conversion import (
    OutputState,
    ProjectState,
    SubtitleState,
    build_project_snapshot,
    restore_project_state,
)
from bdsubmerge.project.schema import (
    BoundarySnapshot,
    ConflictPolicySnapshot,
    MappingSnapshot,
    SourceState,
)


def test_state_snapshot_restore_preserves_application_contract(tmp_path: Path) -> None:
    project_file = tmp_path / "project" / "show.bdsm.json"
    bdmv = tmp_path / "disc" / "BDMV"
    index = bdmv / "index.bdmv"
    playlist = bdmv / "PLAYLIST" / "00001.mpls"
    subtitle_two = tmp_path / "subs" / "E02.ass"
    subtitle_one = tmp_path / "subs" / "E01.ass"
    output = bdmv / "index.ass"
    playlist.parent.mkdir(parents=True)
    subtitle_one.parent.mkdir(parents=True)
    index.write_bytes(b"index")
    playlist.write_bytes(b"playlist")
    subtitle_one.write_bytes(b"one")
    subtitle_two.write_bytes(b"two")
    boundaries = (
        BoundarySnapshot(
            "start",
            0,
            ("playlist_start",),
            ("playlist",),
            enabled=True,
        ),
        BoundarySnapshot(
            "end",
            180_000,
            ("chapter",),
            ("mark:0",),
            enabled=False,
            user_created=True,
            note="locked boundary",
        ),
    )
    mappings = (
        MappingSnapshot("E01", "start", "end", 0, 180_000, 900, True, "high"),
    )
    state = ProjectState(
        bdmv,
        index,
        playlist,
        "00001",
        180_000,
        (("00001", 0, 90_000, 0),),
        (
            SubtitleState("E02", subtitle_two, "ass", "utf-8", 1),
            SubtitleState(
                "E01",
                subtitle_one,
                "ass",
                "utf-8-sig",
                0,
                170_000,
                160_000,
                30,
                4,
                (("language", "zh-CN"),),
                ("tail",),
            ),
        ),
        boundaries,
        mappings,
        (OutputState("main", "jriver", "", output, "utf-8-sig", "abort"),),
        ConflictPolicySnapshot(accept_script_info_conflicts=True),
        "reviewed",
    )

    snapshot = build_project_snapshot(state, project_file=project_file)
    restored = restore_project_state(snapshot, project_file=project_file)

    assert [item.id for item in snapshot.subtitles] == ["E01", "E02"]
    assert [item.id for item in restored.state.subtitles] == ["E01", "E02"]
    assert restored.state.subtitles[0].encoding == "utf-8-sig"
    assert restored.state.subtitles[0].metadata == (("language", "zh-CN"),)
    assert restored.state.boundaries == boundaries
    assert restored.state.mappings == mappings
    assert restored.state.outputs[0].resolved_path == output.absolute()
    assert restored.state.conflict_policy.accept_script_info_conflicts is True
    assert restored.state.ui_notes == "reviewed"
    assert all(check.state is SourceState.UNCHANGED for check in restored.source_checks)
    assert {check.id for check in restored.source_checks} == {
        "bdmv",
        "index_bdmv",
        "playlist",
        "E01",
        "E02",
    }
    assert restored.has_changed_sources is False


def test_restore_exposes_changed_source_before_application_use(tmp_path: Path) -> None:
    project_file = tmp_path / "show.bdsm.json"
    bdmv = tmp_path / "BDMV"
    bdmv.mkdir()
    index = bdmv / "index.bdmv"
    playlist = bdmv / "00001.mpls"
    subtitle = tmp_path / "E01.srt"
    for path in (index, playlist, subtitle):
        path.write_bytes(b"old")
    state = ProjectState(
        bdmv,
        index,
        playlist,
        "00001",
        90_000,
        (),
        (SubtitleState("E01", subtitle, "srt", "utf-8-sig", 0),),
        (
            BoundarySnapshot("start", 0),
            BoundarySnapshot("end", 90_000),
        ),
        (MappingSnapshot("E01", "start", "end", 0, 90_000),),
        (),
    )
    snapshot = build_project_snapshot(state, project_file=project_file)
    subtitle.write_bytes(b"changed source")

    restored = restore_project_state(snapshot, project_file=project_file)

    subtitle_check = next(check for check in restored.source_checks if check.id == "E01")
    assert subtitle_check.state is SourceState.CHANGED
    assert restored.has_changed_sources is True
