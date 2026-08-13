"""Shared project-source relocation workflow for CLI and GUI surfaces."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .conversion import RestoredProject, restore_project_state
from .paths import (
    check_directory,
    check_file,
    fingerprint,
    relocate_source,
)
from .schema import (
    FileFingerprint,
    FileSnapshot,
    ProjectSnapshot,
    SourceCheck,
    SourceState,
)


class ProjectSourceRelocationError(ValueError):
    """A requested source relocation is invalid or unsafe."""


class RelocationConfirmationRequiredError(ProjectSourceRelocationError):
    """The selected source changed and requires explicit confirmation."""


@dataclass(frozen=True, slots=True)
class FindRelocationCandidatesRequest:
    project: ProjectSnapshot
    project_file: Path
    source_id: str
    search_roots: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class RelocationCandidate:
    path: Path
    actual: FileFingerprint
    state: SourceState

    @property
    def requires_confirmation(self) -> bool:
        return self.state is SourceState.CHANGED


@dataclass(frozen=True, slots=True)
class FindRelocationCandidatesResult:
    source: SourceCheck
    candidates: tuple[RelocationCandidate, ...]


@dataclass(frozen=True, slots=True)
class RelocateProjectSourceRequest:
    project: ProjectSnapshot
    project_file: Path
    source_id: str
    selected_path: Path
    confirm_changed_source: bool = False


@dataclass(frozen=True, slots=True)
class RelocateProjectSourceResult:
    project: ProjectSnapshot
    restored: RestoredProject
    candidate: RelocationCandidate
    source: SourceCheck


@dataclass(frozen=True, slots=True)
class _ProjectSource:
    snapshot: FileSnapshot
    is_directory: bool


class ProjectSourceRelocationService:
    """Find and explicitly apply source relocations without writing source data."""

    def find_candidates(
        self,
        request: FindRelocationCandidatesRequest,
    ) -> FindRelocationCandidatesResult:
        source = _project_source(request.project, request.source_id)
        current = _check_source(
            request.source_id,
            source,
            project_file=request.project_file,
        )
        candidates: list[RelocationCandidate] = []
        seen: set[str] = set()
        wanted_name = source.snapshot.path.name.casefold()
        for search_root in request.search_roots:
            for path in _matching_paths(
                search_root,
                wanted_name=wanted_name,
                is_directory=source.is_directory,
            ):
                identity = _path_identity(path)
                if identity in seen:
                    continue
                try:
                    candidate = _inspect_candidate(path, source)
                except OSError:
                    continue
                seen.add(identity)
                candidates.append(candidate)
        candidates.sort(
            key=lambda item: (
                item.requires_confirmation,
                str(item.path).casefold(),
                str(item.path),
            )
        )
        return FindRelocationCandidatesResult(current, tuple(candidates))

    def relocate(
        self,
        request: RelocateProjectSourceRequest,
    ) -> RelocateProjectSourceResult:
        source = _project_source(request.project, request.source_id)
        try:
            candidate = _inspect_candidate(request.selected_path, source)
        except OSError as error:
            raise ProjectSourceRelocationError(str(error)) from error
        _validate_selected_path(
            request.project,
            request.source_id,
            request.selected_path,
            project_file=request.project_file,
        )
        if candidate.requires_confirmation and not request.confirm_changed_source:
            raise RelocationConfirmationRequiredError(
                f"source {request.source_id!r} does not match its saved fingerprint"
            )
        relocated = relocate_source(
            request.project,
            request.source_id,
            candidate.path,
            project_file=request.project_file,
            refresh_fingerprint=True,
        )
        if not source.is_directory:
            refreshed = _project_source(relocated, request.source_id).snapshot.fingerprint
            if refreshed != candidate.actual:
                raise ProjectSourceRelocationError(
                    f"source {request.source_id!r} changed while applying relocation"
                )
        if request.source_id == "bdmv":
            relocated = _relocate_bdmv_children(
                relocated,
                candidate.path,
                project_file=request.project_file,
            )
        restored = restore_project_state(relocated, project_file=request.project_file)
        relocated_check = next(
            check for check in restored.source_checks if check.id == request.source_id
        )
        return RelocateProjectSourceResult(
            relocated,
            restored,
            candidate,
            relocated_check,
        )


def _project_source(project: ProjectSnapshot, source_id: str) -> _ProjectSource:
    if source_id == "bdmv":
        return _ProjectSource(project.bdmv, True)
    if source_id == "index_bdmv":
        return _ProjectSource(project.index_bdmv, False)
    if source_id == "playlist":
        return _ProjectSource(project.playlist.source, False)
    for subtitle in project.subtitles:
        if subtitle.id == source_id:
            return _ProjectSource(subtitle.source, False)
    raise KeyError(f"unknown project source id: {source_id}")


def _check_source(
    source_id: str,
    source: _ProjectSource,
    *,
    project_file: Path,
) -> SourceCheck:
    if source.is_directory:
        return check_directory(source_id, source.snapshot, project_file=project_file)
    return check_file(source_id, source.snapshot, project_file=project_file)


def _matching_paths(
    search_root: Path,
    *,
    wanted_name: str,
    is_directory: bool,
) -> tuple[Path, ...]:
    if not search_root.is_dir():
        return ()
    matches: list[Path] = []
    if is_directory and search_root.name.casefold() == wanted_name:
        matches.append(search_root)
    try:
        descendants = search_root.rglob("*")
        matches.extend(
            path
            for path in descendants
            if path.name.casefold() == wanted_name
            and (path.is_dir() if is_directory else path.is_file())
        )
    except OSError:
        return tuple(matches)
    return tuple(matches)


def _inspect_candidate(path: Path, source: _ProjectSource) -> RelocationCandidate:
    if source.is_directory:
        if not path.is_dir():
            raise NotADirectoryError(f"relocated BDMV source is not a directory: {path}")
    elif not path.is_file():
        if path.is_dir():
            raise IsADirectoryError(f"relocated source is not a file: {path}")
        raise FileNotFoundError(f"relocated source does not exist: {path}")
    actual = fingerprint(path)
    state = (
        SourceState.UNCHANGED
        if source.is_directory or actual == source.snapshot.fingerprint
        else SourceState.CHANGED
    )
    return RelocationCandidate(path, actual, state)


def _validate_selected_path(
    project: ProjectSnapshot,
    source_id: str,
    path: Path,
    *,
    project_file: Path,
) -> None:
    if source_id == "bdmv":
        if path.name.casefold() != "bdmv":
            raise ProjectSourceRelocationError(
                f"relocated BDMV source must be a BDMV directory: {path}"
            )
        return
    if source_id == "index_bdmv":
        if path.name.casefold() != "index.bdmv":
            raise ProjectSourceRelocationError(
                f"relocated index source must be named index.bdmv: {path}"
            )
        expected_bdmv = check_directory(
            "bdmv",
            project.bdmv,
            project_file=project_file,
        ).path
        if not _same_path(path.parent, expected_bdmv):
            raise ProjectSourceRelocationError(
                f"relocated index source must belong to the selected BDMV: {path}"
            )
        return
    if source_id == "playlist":
        if path.suffix.casefold() != ".mpls":
            raise ProjectSourceRelocationError(
                f"relocated playlist source must be an MPLS file: {path}"
            )
        if path.stem.casefold() != project.playlist.stem.casefold():
            raise ProjectSourceRelocationError(
                "relocated playlist source must keep the saved playlist stem: "
                f"{path}"
            )
        expected_bdmv = check_directory(
            "bdmv",
            project.bdmv,
            project_file=project_file,
        ).path
        if (
            path.parent.name.casefold() != "playlist"
            or not _same_path(path.parent.parent, expected_bdmv)
        ):
            raise ProjectSourceRelocationError(
                f"relocated playlist source must belong to BDMV/PLAYLIST: {path}"
            )
        return
    subtitle = next(item for item in project.subtitles if item.id == source_id)
    expected_suffix = f".{subtitle.format.casefold()}"
    if path.suffix.casefold() != expected_suffix:
        raise ProjectSourceRelocationError(
            f"relocated subtitle must keep the saved {subtitle.format} format: {path}"
        )


def _relocate_bdmv_children(
    project: ProjectSnapshot,
    bdmv: Path,
    *,
    project_file: Path,
) -> ProjectSnapshot:
    """Move coupled media locators while preserving their saved fingerprints."""

    relocated = relocate_source(
        project,
        "index_bdmv",
        bdmv / "index.bdmv",
        project_file=project_file,
    )
    return relocate_source(
        relocated,
        "playlist",
        bdmv / "PLAYLIST" / f"{project.playlist.stem}.mpls",
        project_file=project_file,
    )


def _same_path(left: Path, right: Path) -> bool:
    left_value = str(left.absolute())
    right_value = str(right.absolute())
    if os.name == "nt":
        return left_value.casefold() == right_value.casefold()
    return left_value == right_value


def _path_identity(path: Path) -> str:
    absolute = str(path.resolve(strict=False))
    return absolute.casefold() if os.name == "nt" else absolute
