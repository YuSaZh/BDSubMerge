import os
from dataclasses import replace
from pathlib import Path

import pytest
from test_project_persistence import sample_project

from bdsubmerge.project.paths import fingerprint, snapshot_file, store_path
from bdsubmerge.project.relocation import (
    FindRelocationCandidatesRequest,
    ProjectSourceRelocationError,
    ProjectSourceRelocationService,
    RelocateProjectSourceRequest,
    RelocationConfirmationRequiredError,
)
from bdsubmerge.project.schema import SourceState


def test_candidate_search_classifies_and_ranks_fingerprint_matches(
    tmp_path: Path,
) -> None:
    project_file = tmp_path / "project" / "show.bdsm.json"
    missing_source = tmp_path / "old" / "E01.ass"
    exact = tmp_path / "library" / "exact" / "e01.ASS"
    changed = tmp_path / "library" / "changed" / "E01.ass"
    exact.parent.mkdir(parents=True)
    changed.parent.mkdir(parents=True)
    exact.write_bytes(b"expected")
    changed.write_bytes(b"different")
    project = sample_project()
    project = replace(
        project,
        subtitles=(
            replace(
                project.subtitles[0],
                source=replace(
                    snapshot_file(exact, project_file=project_file),
                    path=store_path(missing_source, project_file=project_file),
                ),
            ),
        ),
    )

    result = ProjectSourceRelocationService().find_candidates(
        FindRelocationCandidatesRequest(
            project,
            project_file,
            "E01",
            (tmp_path / "library", tmp_path / "library" / "exact"),
        )
    )

    assert result.source.path == missing_source
    assert result.source.state is SourceState.MISSING
    assert tuple(candidate.path for candidate in result.candidates) == (exact, changed)
    assert result.candidates[0].state is SourceState.UNCHANGED
    assert result.candidates[0].requires_confirmation is False
    assert result.candidates[1].state is SourceState.CHANGED
    assert result.candidates[1].requires_confirmation is True


def test_exact_relocation_returns_new_snapshot_and_restored_state(tmp_path: Path) -> None:
    project_file = tmp_path / "show.bdsm.json"
    relocated_path = tmp_path / "library" / "E01.ass"
    relocated_path.parent.mkdir()
    relocated_path.write_bytes(b"expected")
    project = sample_project()
    source = replace(
        project.subtitles[0].source,
        fingerprint=fingerprint(relocated_path),
    )
    project = replace(
        project,
        subtitles=(replace(project.subtitles[0], source=source),),
    )

    result = ProjectSourceRelocationService().relocate(
        RelocateProjectSourceRequest(project, project_file, "E01", relocated_path)
    )

    assert result.project is not project
    assert project.subtitles[0].source.path == source.path
    assert result.project.subtitles[0].source.fingerprint == fingerprint(relocated_path)
    assert result.restored.state.subtitles[0].path == relocated_path.absolute()
    assert result.source.state is SourceState.UNCHANGED
    assert result.candidate.requires_confirmation is False


def test_changed_relocation_requires_confirmation_then_refreshes_fingerprint(
    tmp_path: Path,
) -> None:
    project_file = tmp_path / "show.bdsm.json"
    changed = tmp_path / "relocated" / "E01.ass"
    changed.parent.mkdir()
    changed.write_bytes(b"changed source")
    project = sample_project()
    service = ProjectSourceRelocationService()

    with pytest.raises(RelocationConfirmationRequiredError, match="saved fingerprint"):
        service.relocate(
            RelocateProjectSourceRequest(project, project_file, "E01", changed)
        )

    result = service.relocate(
        RelocateProjectSourceRequest(
            project,
            project_file,
            "E01",
            changed,
            confirm_changed_source=True,
        )
    )

    assert result.candidate.state is SourceState.CHANGED
    assert result.project.subtitles[0].source.fingerprint == fingerprint(changed)
    assert result.source.state is SourceState.UNCHANGED
    assert result.restored.state.subtitles[0].path == changed.absolute()


@pytest.mark.parametrize("source_id", ("index_bdmv", "playlist"))
def test_project_media_file_sources_use_the_same_relocation_workflow(
    tmp_path: Path,
    source_id: str,
) -> None:
    project_file = tmp_path / "show.bdsm.json"
    selected = tmp_path / "disc" / "BDMV" / (
        "index.bdmv"
        if source_id == "index_bdmv"
        else "PLAYLIST/00001.mpls"
    )
    selected.parent.mkdir(parents=True)
    selected.write_bytes(b"relocated media metadata")
    project = sample_project()
    project = replace(
        project,
        bdmv=replace(
            project.bdmv,
            path=store_path(
                selected.parent
                if source_id == "index_bdmv"
                else selected.parents[1],
                project_file=project_file,
            ),
        ),
    )

    result = ProjectSourceRelocationService().relocate(
        RelocateProjectSourceRequest(
            project,
            project_file,
            source_id,
            selected,
            confirm_changed_source=True,
        )
    )

    expected_source = (
        result.project.index_bdmv
        if source_id == "index_bdmv"
        else result.project.playlist.source
    )
    expected_path = (
        result.restored.state.index_bdmv_path
        if source_id == "index_bdmv"
        else result.restored.state.playlist_path
    )
    assert expected_source.fingerprint == fingerprint(selected)
    assert expected_path == selected.absolute()
    assert result.source.state is SourceState.UNCHANGED


@pytest.mark.parametrize(
    ("source_id", "selected", "message"),
    (
        ("index_bdmv", Path("other/index.bdmv"), "selected BDMV"),
        ("playlist", Path("other/00001.mpls"), "BDMV/PLAYLIST"),
        ("playlist", Path("disc/BDMV/PLAYLIST/99999.mpls"), "playlist stem"),
        ("E01", Path("subs/E01.srt"), "saved ass format"),
    ),
)
def test_relocation_rejects_wrong_source_role_or_tree(
    tmp_path: Path,
    source_id: str,
    selected: Path,
    message: str,
) -> None:
    project_file = tmp_path / "show.bdsm.json"
    bdmv = tmp_path / "disc" / "BDMV"
    bdmv.mkdir(parents=True)
    candidate = tmp_path / selected
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b"candidate")
    project = sample_project()
    project = replace(
        project,
        bdmv=replace(
            project.bdmv,
            path=store_path(bdmv, project_file=project_file),
        ),
    )

    with pytest.raises(ProjectSourceRelocationError, match=message):
        ProjectSourceRelocationService().relocate(
            RelocateProjectSourceRequest(
                project,
                project_file,
                source_id,
                candidate,
                confirm_changed_source=True,
            )
        )


def test_relocation_rejects_missing_paths_and_wrong_source_kind(tmp_path: Path) -> None:
    project_file = tmp_path / "show.bdsm.json"
    directory = tmp_path / "directory"
    directory.mkdir()
    service = ProjectSourceRelocationService()

    with pytest.raises(ProjectSourceRelocationError, match="does not exist"):
        service.relocate(
            RelocateProjectSourceRequest(
                sample_project(),
                project_file,
                "E01",
                tmp_path / "missing.ass",
            )
        )
    with pytest.raises(ProjectSourceRelocationError, match="not a file"):
        service.relocate(
            RelocateProjectSourceRequest(
                sample_project(),
                project_file,
                "E01",
                directory,
            )
        )


def test_relocation_rejects_file_changed_while_applying_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_file = tmp_path / "show.bdsm.json"
    selected = tmp_path / "episode.ass"
    selected.write_bytes(b"selected")
    project = sample_project()
    expected = project.subtitles[0].source.fingerprint
    changed = replace(expected, size=expected.size + 1)
    monkeypatch.setattr(
        "bdsubmerge.project.relocation.fingerprint",
        lambda _path: expected,
    )
    monkeypatch.setattr(
        "bdsubmerge.project.paths.fingerprint",
        lambda _path: changed,
    )

    with pytest.raises(ProjectSourceRelocationError, match="changed while applying"):
        ProjectSourceRelocationService().relocate(
            RelocateProjectSourceRequest(project, project_file, "E01", selected)
        )


def test_unknown_source_id_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="unknown project source id"):
        ProjectSourceRelocationService().find_candidates(
            FindRelocationCandidatesRequest(
                sample_project(),
                tmp_path / "show.bdsm.json",
                "unknown",
                (tmp_path,),
            )
        )


def test_bdmv_directory_relocation_only_reads_selected_directory(tmp_path: Path) -> None:
    project_file = tmp_path / "show.bdsm.json"
    bdmv = tmp_path / "disc" / "BDMV"
    bdmv.mkdir(parents=True)
    marker = bdmv / "index.bdmv"
    marker.write_bytes(b"read only")
    project = sample_project()

    result = ProjectSourceRelocationService().relocate(
        RelocateProjectSourceRequest(project, project_file, "bdmv", bdmv)
    )

    assert result.restored.state.bdmv_path == bdmv.absolute()
    assert result.project.bdmv.fingerprint == fingerprint(bdmv)
    assert result.source.state is SourceState.UNCHANGED
    assert marker.read_bytes() == b"read only"


def test_bdmv_relocation_moves_coupled_media_paths_without_trusting_changes(
    tmp_path: Path,
) -> None:
    project_file = tmp_path / "show.bdsm.json"
    old_bdmv = tmp_path / "old" / "BDMV"
    new_bdmv = tmp_path / "new" / "BDMV"
    old_playlist = old_bdmv / "PLAYLIST" / "00001.mpls"
    new_playlist = new_bdmv / "PLAYLIST" / "00001.mpls"
    old_playlist.parent.mkdir(parents=True)
    new_playlist.parent.mkdir(parents=True)
    old_index = old_bdmv / "index.bdmv"
    new_index = new_bdmv / "index.bdmv"
    old_index.write_bytes(b"saved index")
    old_playlist.write_bytes(b"saved playlist")
    new_index.write_bytes(b"changed index")
    new_playlist.write_bytes(b"saved playlist")
    old_playlist_stat = old_playlist.stat()
    os.utime(
        new_playlist,
        ns=(old_playlist_stat.st_atime_ns, old_playlist_stat.st_mtime_ns),
    )
    project = sample_project()
    project = replace(
        project,
        bdmv=snapshot_file(old_bdmv, project_file=project_file),
        index_bdmv=snapshot_file(old_index, project_file=project_file),
        playlist=replace(
            project.playlist,
            source=snapshot_file(old_playlist, project_file=project_file),
        ),
    )

    result = ProjectSourceRelocationService().relocate(
        RelocateProjectSourceRequest(project, project_file, "bdmv", new_bdmv)
    )

    checks = {check.id: check for check in result.restored.source_checks}
    assert result.restored.state.bdmv_path == new_bdmv.absolute()
    assert result.restored.state.index_bdmv_path == new_index.absolute()
    assert result.restored.state.playlist_path == new_playlist.absolute()
    assert checks["bdmv"].state is SourceState.UNCHANGED
    assert checks["index_bdmv"].state is SourceState.CHANGED
    assert checks["playlist"].state is SourceState.UNCHANGED
    assert result.project.index_bdmv.fingerprint == fingerprint(old_index)
    assert result.project.playlist.source.fingerprint == fingerprint(old_playlist)


def test_bdmv_relocation_rejects_a_file(tmp_path: Path) -> None:
    selected_file = tmp_path / "BDMV"
    selected_file.write_bytes(b"not a directory")

    with pytest.raises(ProjectSourceRelocationError, match="not a directory"):
        ProjectSourceRelocationService().relocate(
            RelocateProjectSourceRequest(
                sample_project(),
                tmp_path / "show.bdsm.json",
                "bdmv",
                selected_file,
            )
        )
