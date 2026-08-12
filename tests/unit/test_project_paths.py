import os
from dataclasses import replace
from pathlib import Path

from test_project_persistence import sample_project

from bdsubmerge.project.paths import (
    check_project_sources,
    find_relocation_candidates,
    fingerprint,
    relocate_source,
    resolve_path,
    snapshot_file,
    store_path,
)
from bdsubmerge.project.schema import SourceState, StoredPath


def test_path_in_project_tree_prefers_relative_location(tmp_path: Path) -> None:
    project_file = tmp_path / "project" / "show.bdsm.json"
    subtitle = project_file.parent / "subs" / "E01.ass"
    subtitle.parent.mkdir(parents=True)
    subtitle.write_text("subtitle", encoding="utf-8")

    stored = store_path(subtitle, project_file=project_file)

    assert stored.relative == "subs/E01.ass"
    assert resolve_path(stored, project_file=project_file) == subtitle.absolute()


def test_sibling_path_is_stored_relative_to_project(tmp_path: Path) -> None:
    project_file = tmp_path / "projects" / "show.bdsm.json"
    subtitle = tmp_path / "subs" / "E01.ass"
    subtitle.parent.mkdir()
    subtitle.write_text("subtitle", encoding="utf-8")

    stored = store_path(subtitle, project_file=project_file)

    assert stored.relative == "../subs/E01.ass"


def test_absolute_hint_is_used_after_project_moves(tmp_path: Path) -> None:
    existing = tmp_path / "media" / "E01.ass"
    existing.parent.mkdir()
    existing.write_text("subtitle", encoding="utf-8")
    stored = StoredPath("missing/E01.ass", str(existing.absolute()))

    resolved = resolve_path(stored, project_file=tmp_path / "moved" / "project.bdsm.json")

    assert resolved == existing.absolute()


def test_metadata_fingerprint_detects_change_and_missing_sources(tmp_path: Path) -> None:
    project_file = tmp_path / "show.bdsm.json"
    index = tmp_path / "index.bdmv"
    playlist = tmp_path / "00001.mpls"
    subtitle = tmp_path / "E01.ass"
    bdmv = tmp_path / "BDMV"
    bdmv.mkdir()
    for path, content in ((index, "index"), (playlist, "playlist"), (subtitle, "subtitle")):
        path.write_text(content, encoding="utf-8")
    project = sample_project()
    project = replace(
        project,
        bdmv=snapshot_file(bdmv, project_file=project_file),
        index_bdmv=snapshot_file(index, project_file=project_file),
        playlist=replace(
            project.playlist,
            source=snapshot_file(playlist, project_file=project_file),
        ),
        subtitles=(
            replace(
                project.subtitles[0],
                source=snapshot_file(subtitle, project_file=project_file),
            ),
        ),
    )
    subtitle.write_text("subtitle changed", encoding="utf-8")
    os.utime(subtitle, ns=(subtitle.stat().st_atime_ns, subtitle.stat().st_mtime_ns + 1))
    playlist.unlink()

    checks = {
        check.id: check
        for check in check_project_sources(project, project_file=project_file)
    }

    assert checks["index_bdmv"].state is SourceState.UNCHANGED
    assert checks["bdmv"].state is SourceState.UNCHANGED
    assert checks["playlist"].state is SourceState.MISSING
    assert checks["E01"].state is SourceState.CHANGED
    assert checks["E01"].actual == fingerprint(subtitle)


def test_relocation_preserves_or_explicitly_refreshes_fingerprint(tmp_path: Path) -> None:
    project_file = tmp_path / "show.bdsm.json"
    new_subtitle = tmp_path / "relocated" / "E01.ass"
    new_subtitle.parent.mkdir()
    new_subtitle.write_text("new source", encoding="utf-8")
    project = sample_project()
    original = project.subtitles[0].source.fingerprint

    relocated = relocate_source(project, "E01", new_subtitle, project_file=project_file)
    refreshed = relocate_source(
        project,
        "E01",
        new_subtitle,
        project_file=project_file,
        refresh_fingerprint=True,
    )

    assert relocated.subtitles[0].source.fingerprint == original
    assert refreshed.subtitles[0].source.fingerprint == fingerprint(new_subtitle)
    assert project.subtitles[0].source.fingerprint == original


def test_candidate_search_matches_name_without_content_hashing(tmp_path: Path) -> None:
    candidate = tmp_path / "library" / "season" / "E01.ass"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("anything", encoding="utf-8")
    source = sample_project().subtitles[0].source

    matches = find_relocation_candidates(source, (tmp_path / "library",))

    assert matches == (candidate,)


def test_bdmv_check_ignores_directory_mtime_changes_from_output(tmp_path: Path) -> None:
    project_file = tmp_path / "show.bdsm.json"
    bdmv = tmp_path / "BDMV"
    bdmv.mkdir()
    project = replace(
        sample_project(),
        bdmv=snapshot_file(bdmv, project_file=project_file),
    )
    (bdmv / "index.ass").write_text("output", encoding="utf-8")

    bdmv_check = next(
        check
        for check in check_project_sources(project, project_file=project_file)
        if check.id == "bdmv"
    )

    assert bdmv_check.state is SourceState.UNCHANGED
