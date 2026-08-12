"""Neutral application-state DTOs and project snapshot conversion."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .paths import check_project_sources, resolve_path, snapshot_file, store_path
from .schema import (
    BoundarySnapshot,
    ConflictPolicySnapshot,
    MappingSnapshot,
    OutputSnapshot,
    PlaylistSnapshot,
    ProjectSnapshot,
    SourceCheck,
    SourceState,
    SubtitleSnapshot,
)


@dataclass(frozen=True, slots=True)
class SubtitleState:
    id: str
    path: Path
    format: str
    encoding: str
    order: int
    raw_end_90k: int | None = None
    effective_end_90k: int | None = None
    event_count: int = 0
    style_count: int = 0
    metadata: tuple[tuple[str, str], ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OutputState:
    id: str
    preset: str
    path_template: str
    resolved_path: Path | None
    encoding: str
    collision_policy: str
    backup_policy: str = "none"


@dataclass(frozen=True, slots=True)
class ProjectState:
    bdmv_path: Path
    index_bdmv_path: Path
    playlist_path: Path
    playlist_stem: str
    playlist_duration_90k: int
    playlist_timeline_fingerprint: tuple[tuple[str, int, int, int], ...]
    subtitles: tuple[SubtitleState, ...]
    boundaries: tuple[BoundarySnapshot, ...]
    mappings: tuple[MappingSnapshot, ...]
    outputs: tuple[OutputState, ...]
    conflict_policy: ConflictPolicySnapshot = field(default_factory=ConflictPolicySnapshot)
    ui_notes: str = ""


@dataclass(frozen=True, slots=True)
class RestoredProject:
    state: ProjectState
    source_checks: tuple[SourceCheck, ...]

    @property
    def has_changed_sources(self) -> bool:
        return any(check.state is not SourceState.UNCHANGED for check in self.source_checks)


def build_project_snapshot(
    state: ProjectState,
    *,
    project_file: Path,
) -> ProjectSnapshot:
    """Capture reproducible metadata from a neutral application state."""

    subtitles = tuple(
        SubtitleSnapshot(
            item.id,
            snapshot_file(item.path, project_file=project_file),
            item.format,
            item.encoding,
            item.order,
            item.raw_end_90k,
            item.effective_end_90k,
            item.event_count,
            item.style_count,
            item.metadata,
            item.warnings,
        )
        for item in sorted(state.subtitles, key=lambda item: item.order)
    )
    outputs = tuple(
        OutputSnapshot(
            item.id,
            item.preset,
            item.path_template,
            (
                store_path(item.resolved_path, project_file=project_file)
                if item.resolved_path is not None
                else None
            ),
            item.encoding,
            item.collision_policy,
            item.backup_policy,
        )
        for item in state.outputs
    )
    return ProjectSnapshot(
        snapshot_file(state.bdmv_path, project_file=project_file),
        snapshot_file(state.index_bdmv_path, project_file=project_file),
        PlaylistSnapshot(
            snapshot_file(state.playlist_path, project_file=project_file),
            state.playlist_stem,
            state.playlist_duration_90k,
            state.playlist_timeline_fingerprint,
        ),
        subtitles,
        state.boundaries,
        state.mappings,
        outputs,
        state.conflict_policy,
        state.ui_notes,
    )


def restore_project_state(
    project: ProjectSnapshot,
    *,
    project_file: Path,
) -> RestoredProject:
    """Resolve paths and return the application request state plus source checks."""

    subtitles = tuple(
        SubtitleState(
            item.id,
            resolve_path(item.source.path, project_file=project_file),
            item.format,
            item.encoding,
            item.order,
            item.raw_end_90k,
            item.effective_end_90k,
            item.event_count,
            item.style_count,
            item.metadata,
            item.warnings,
        )
        for item in sorted(project.subtitles, key=lambda item: item.order)
    )
    outputs = tuple(
        OutputState(
            item.id,
            item.preset,
            item.path_template,
            (
                resolve_path(item.resolved_path, project_file=project_file)
                if item.resolved_path is not None
                else None
            ),
            item.encoding,
            item.collision_policy,
            item.backup_policy,
        )
        for item in project.outputs
    )
    state = ProjectState(
        resolve_path(project.bdmv.path, project_file=project_file),
        resolve_path(project.index_bdmv.path, project_file=project_file),
        resolve_path(project.playlist.source.path, project_file=project_file),
        project.playlist.stem,
        project.playlist.duration_90k,
        project.playlist.timeline_fingerprint,
        subtitles,
        project.boundaries,
        project.mappings,
        outputs,
        project.conflict_policy,
        project.ui_notes,
    )
    return RestoredProject(
        state,
        check_project_sources(project, project_file=project_file),
    )
