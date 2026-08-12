"""Path storage, resolution, source checks, and explicit relocation."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from .schema import (
    FileFingerprint,
    FileSnapshot,
    ProjectSnapshot,
    SourceCheck,
    SourceState,
    StoredPath,
)


def store_path(path: Path, *, project_file: Path) -> StoredPath:
    """Prefer a path relative to the project directory when it shares a tree."""

    absolute = path.absolute()
    project_directory = project_file.absolute().parent
    try:
        common = Path(os.path.commonpath((absolute, project_directory)))
        if common == Path(common.anchor):
            raise ValueError("paths share only the filesystem root")
        candidate = Path(os.path.relpath(absolute, project_directory))
    except ValueError:
        relative: str | None = None
    else:
        relative = candidate.as_posix()
    return StoredPath(relative, str(absolute))


def resolve_path(stored: StoredPath, *, project_file: Path) -> Path:
    """Resolve relative location first, then use the absolute recovery hint."""

    if stored.relative is not None:
        relative_candidate = project_file.absolute().parent / Path(stored.relative)
        if relative_candidate.exists():
            return relative_candidate
    return Path(stored.absolute)


def resolve_output_path(stored: StoredPath, *, project_file: Path) -> Path:
    """Resolve a destination relative to the project even before it exists."""

    if stored.relative is not None:
        return project_file.absolute().parent / Path(stored.relative)
    return Path(stored.absolute)


def fingerprint(path: Path) -> FileFingerprint:
    stat = path.stat()
    return FileFingerprint(stat.st_size, stat.st_mtime_ns)


def snapshot_file(path: Path, *, project_file: Path) -> FileSnapshot:
    return FileSnapshot(store_path(path, project_file=project_file), fingerprint(path))


def check_file(
    source_id: str,
    source: FileSnapshot,
    *,
    project_file: Path,
) -> SourceCheck:
    path = resolve_path(source.path, project_file=project_file)
    try:
        actual = fingerprint(path)
    except FileNotFoundError:
        return SourceCheck(source_id, path, SourceState.MISSING, source.fingerprint, None)
    state = SourceState.UNCHANGED if actual == source.fingerprint else SourceState.CHANGED
    return SourceCheck(source_id, path, state, source.fingerprint, actual)


def check_directory(
    source_id: str,
    source: FileSnapshot,
    *,
    project_file: Path,
) -> SourceCheck:
    """Check a locator directory without treating output creation as source mutation."""

    path = resolve_path(source.path, project_file=project_file)
    if not path.is_dir():
        return SourceCheck(source_id, path, SourceState.MISSING, source.fingerprint, None)
    return SourceCheck(
        source_id,
        path,
        SourceState.UNCHANGED,
        source.fingerprint,
        fingerprint(path),
    )


def check_project_sources(
    project: ProjectSnapshot,
    *,
    project_file: Path,
) -> tuple[SourceCheck, ...]:
    checks = [check_directory("bdmv", project.bdmv, project_file=project_file)]
    checks.append(check_file("index_bdmv", project.index_bdmv, project_file=project_file))
    checks.append(check_file("playlist", project.playlist.source, project_file=project_file))
    checks.extend(
        check_file(subtitle.id, subtitle.source, project_file=project_file)
        for subtitle in project.subtitles
    )
    return tuple(checks)


def relocate_source(
    project: ProjectSnapshot,
    source_id: str,
    new_path: Path,
    *,
    project_file: Path,
    refresh_fingerprint: bool = False,
) -> ProjectSnapshot:
    """Return a new snapshot with one explicitly relocated source."""

    stored = store_path(new_path, project_file=project_file)

    def relocated(source: FileSnapshot) -> FileSnapshot:
        new_fingerprint = fingerprint(new_path) if refresh_fingerprint else source.fingerprint
        return replace(source, path=stored, fingerprint=new_fingerprint)

    if source_id == "index_bdmv":
        return replace(project, index_bdmv=relocated(project.index_bdmv))
    if source_id == "bdmv":
        return replace(project, bdmv=relocated(project.bdmv))
    if source_id == "playlist":
        return replace(
            project,
            playlist=replace(project.playlist, source=relocated(project.playlist.source)),
        )
    subtitles = list(project.subtitles)
    for index, subtitle in enumerate(subtitles):
        if subtitle.id == source_id:
            subtitles[index] = replace(subtitle, source=relocated(subtitle.source))
            return replace(project, subtitles=tuple(subtitles))
    raise KeyError(f"unknown project source id: {source_id}")


def find_relocation_candidates(
    source: FileSnapshot,
    search_roots: tuple[Path, ...],
) -> tuple[Path, ...]:
    """Find same-name files without reading or hashing their content."""

    name = source.path.name
    matches: list[Path] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        matches.extend(candidate for candidate in root.rglob(name) if candidate.is_file())
    return tuple(sorted(set(matches), key=lambda path: str(path).casefold()))
