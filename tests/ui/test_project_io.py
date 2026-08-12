from pathlib import Path

import pytest

from bdsubmerge.project import (
    BoundarySnapshot,
    ConflictPolicySnapshot,
    MappingSnapshot,
    OutputState,
    ProjectState,
    SubtitleState,
)
from bdsubmerge.ui.project_io import (
    capture_and_save,
    load_restored_project,
    qt_atomic_project_writer,
)


def test_qsavefile_writer_atomically_commits_bytes(tmp_path: Path) -> None:
    path = tmp_path / "project.bdsm.json"

    qt_atomic_project_writer(path, b'{"schema_version": 1}\n')

    assert path.read_bytes() == b'{"schema_version": 1}\n'


def test_project_io_does_not_create_parent_directories_implicitly(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "project.bdsm.json"

    with pytest.raises(OSError):
        qt_atomic_project_writer(path, b"{}")

    assert not path.exists()


def test_project_state_round_trip_uses_neutral_project_conversion(tmp_path: Path) -> None:
    bdmv = tmp_path / "Title" / "BDMV"
    playlist = bdmv / "PLAYLIST" / "00001.mpls"
    subtitle = tmp_path / "episode.ass"
    playlist.parent.mkdir(parents=True)
    bdmv.mkdir(exist_ok=True)
    (bdmv / "index.bdmv").write_bytes(b"index")
    playlist.write_bytes(b"mpls")
    subtitle.write_bytes(b"subtitle")
    state = ProjectState(
        bdmv,
        bdmv / "index.bdmv",
        playlist,
        "00001",
        90_000,
        (),
        (SubtitleState("episode-1", subtitle, "ass", "utf-8", 0),),
        (
            BoundarySnapshot("start", 0, ("playlist_start",)),
            BoundarySnapshot("end", 90_000, ("playlist_end",)),
        ),
        (MappingSnapshot("episode-1", "start", "end", 0, 90_000),),
        (OutputState("primary", "jriver", "", bdmv / "index.ass", "utf-8", "abort"),),
        ConflictPolicySnapshot(),
        "note",
    )
    project_file = tmp_path / "show.bdsm.json"

    capture_and_save(state, project_file)
    _, restored = load_restored_project(project_file)

    assert restored.state.ui_notes == "note"
    assert restored.state.subtitles[0].path == subtitle
