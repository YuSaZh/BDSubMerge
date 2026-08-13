"""Shared project restoration and reproduction checks for CLI and GUI."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path
from typing import Protocol

from bdsubmerge.cancellation import raise_if_cancelled, report_progress
from bdsubmerge.domain.models import PlaylistInfo
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.mapping import (
    BoundaryKind,
    BoundarySource,
    MappingLock,
    TimelineBoundary,
    boundary,
)
from bdsubmerge.merge import MergeOptions
from bdsubmerge.output import CollisionPolicy, FullPathOutputTarget, OutputTarget
from bdsubmerge.project import (
    BoundarySnapshot,
    ProjectSnapshot,
    ProjectState,
    RestoredProject,
    SourceCheck,
    SourceState,
    resolve_output_path,
    restore_project_state,
)

from .models import (
    ApplicationIssue,
    ApplicationSeverity,
    LoadSubtitlesRequest,
    LoadSubtitlesResult,
    PreparedMerge,
    PrepareMergeRequest,
    ScanRequest,
    ScanResult,
    SubtitleInput,
)
from .reporting import MergeReportTarget
from .services import build_playlist_boundaries


class ProjectBdmvService(Protocol):
    def scan(self, request: ScanRequest) -> ScanResult: ...


class ProjectSubtitleService(Protocol):
    def load_ordered(self, request: LoadSubtitlesRequest) -> LoadSubtitlesResult: ...


class ProjectMergeService(Protocol):
    def prepare(self, request: PrepareMergeRequest) -> PreparedMerge: ...


@dataclass(frozen=True, slots=True)
class ProjectScanIdentityResult:
    playlist: PlaylistInfo | None
    error_code: str | None = None
    error_source: Path | None = None

    @property
    def ready(self) -> bool:
        return self.playlist is not None and self.error_code is None


@dataclass(frozen=True, slots=True)
class ProjectRestoreRequest:
    project: ProjectSnapshot
    project_file: Path
    report_target: MergeReportTarget | None = None
    accept_low_confidence: bool = False


@dataclass(frozen=True, slots=True)
class ProjectRestoreResult:
    project: ProjectSnapshot
    restored: RestoredProject
    scan: ScanResult | None = None
    playlist: PlaylistInfo | None = None
    subtitles: LoadSubtitlesResult | None = None
    prepared: PreparedMerge | None = None
    issues: tuple[ApplicationIssue, ...] = ()

    @property
    def ready(self) -> bool:
        return (
            self.scan is not None
            and self.scan.ready
            and self.playlist is not None
            and self.subtitles is not None
            and self.subtitles.ready
            and self.prepared is not None
            and self.prepared.mapping is not None
            and not _has_errors(self.issues)
        )


class ProjectRestoreApplicationService:
    """Prepare a complete project workspace without mutating UI or project files."""

    def __init__(
        self,
        bdmv_service: ProjectBdmvService,
        subtitle_service: ProjectSubtitleService,
        merge_service: ProjectMergeService,
    ) -> None:
        self._bdmv_service = bdmv_service
        self._subtitle_service = subtitle_service
        self._merge_service = merge_service

    def prepare(self, request: ProjectRestoreRequest) -> ProjectRestoreResult:
        raise_if_cancelled()
        restored = restore_project_state(
            request.project,
            project_file=request.project_file,
        )
        issues = [
            *project_structure_issues(request.project),
            *project_source_issues(restored.source_checks),
        ]
        if _has_errors(issues):
            return ProjectRestoreResult(request.project, restored, issues=tuple(issues))

        report_progress(8, str(restored.state.bdmv_path))
        scan = self._bdmv_service.scan(ScanRequest(restored.state.bdmv_path))
        issues.extend(scan.issues)
        if not scan.ready or scan.layout is None:
            return ProjectRestoreResult(
                request.project,
                restored,
                scan=scan,
                issues=tuple(issues),
            )

        identity = verify_project_scan_identity(restored.state, scan)
        if identity.playlist is None:
            issues.append(_identity_issue(identity))
            return ProjectRestoreResult(
                request.project,
                restored,
                scan=scan,
                issues=tuple(issues),
            )
        playlist = identity.playlist

        raise_if_cancelled()
        ordered_state = tuple(
            sorted(restored.state.subtitles, key=lambda item: item.order)
        )
        subtitles = self._subtitle_service.load_ordered(
            LoadSubtitlesRequest(
                tuple(
                    SubtitleInput(item.path, item.encoding or None)
                    for item in ordered_state
                )
            )
        )
        issues.extend(subtitles.issues)
        issues.extend(
            project_subtitle_identity_issues(
                request.project,
                restored.state,
                subtitles,
            )
        )
        if not subtitles.ready or _has_errors(issues):
            return ProjectRestoreResult(
                request.project,
                restored,
                scan,
                playlist,
                subtitles,
                issues=tuple(issues),
            )

        try:
            additional_boundaries = project_additional_boundaries(
                request.project,
                playlist,
            )
            locks = project_mapping_locks(
                request.project,
                playlist,
                additional_boundaries,
            )
            output_targets = project_output_targets(
                request.project,
                request.project_file,
            )
        except ValueError as error:
            issues.append(
                _error(
                    "project_restore_invalid",
                    str(error),
                    str(request.project_file),
                )
            )
            return ProjectRestoreResult(
                request.project,
                restored,
                scan,
                playlist,
                subtitles,
                issues=tuple(issues),
            )

        policy = request.project.conflict_policy
        prepared = self._merge_service.prepare(
            PrepareMergeRequest(
                scan.layout,
                playlist,
                subtitles,
                output_targets,
                locks=locks,
                merge_options=MergeOptions(
                    playlist_end_ticks=request.project.playlist.duration_90k,
                    accept_script_info_conflicts=(
                        policy.accept_script_info_conflicts
                    ),
                    keep_events_ending_before_zero=(
                        policy.keep_events_ending_before_zero
                    ),
                    clip_negative_starts=policy.clip_negative_starts,
                ),
                additional_boundaries=additional_boundaries,
                accept_low_confidence=request.accept_low_confidence,
                report_target=request.report_target,
            )
        )
        prepared = project_with_saved_lock_states(
            request.project,
            prepared,
            report_target=request.report_target,
        )
        issues.extend(
            project_reproduction_issues(
                request.project,
                restored.state,
                prepared,
            )
        )
        issues.extend(
            issue
            for issue in prepared.issues
            if issue.severity is ApplicationSeverity.ERROR
            and (
                issue.code.startswith("source_")
                or prepared.mapping is None
            )
        )
        if prepared.mapping is None and not any(
            issue.code == "mapping_reproduction_failed" for issue in issues
        ):
            issues.append(
                _error(
                    "mapping_reproduction_failed",
                    "the saved mapping could not be reconstructed",
                    str(request.project_file),
                )
            )
        if _has_errors(issues):
            return ProjectRestoreResult(
                request.project,
                restored,
                scan,
                playlist,
                subtitles,
                prepared,
                tuple(issues),
            )

        updated = project_with_loaded_subtitle_metadata(
            request.project,
            restored.state,
            subtitles,
        )
        checked = restore_project_state(updated, project_file=request.project_file)
        final_source_issues = project_source_issues(checked.source_checks)
        issues.extend(final_source_issues)
        if _has_errors(final_source_issues):
            return ProjectRestoreResult(
                updated,
                checked,
                scan,
                playlist,
                subtitles,
                prepared,
                tuple(issues),
            )

        runtime_restored = project_runtime_state(checked, prepared)
        report_progress(98, str(request.project_file))
        return ProjectRestoreResult(
            updated,
            runtime_restored,
            scan,
            playlist,
            subtitles,
            prepared,
            tuple(issues),
        )


def verify_project_scan_identity(
    state: ProjectState,
    scan: ScanResult,
) -> ProjectScanIdentityResult:
    """Require a scan to resolve the exact media sources saved by a project."""

    layout = scan.layout
    if not scan.ready or layout is None:
        return ProjectScanIdentityResult(None, "project.scan_mismatch")
    if not _same_path(layout.index_bdmv_path, state.index_bdmv_path):
        return ProjectScanIdentityResult(
            None,
            "project.index_mismatch",
            layout.index_bdmv_path,
        )
    playlist = next(
        (
            item
            for item in scan.playlists
            if item.stem.casefold() == state.playlist_stem.casefold()
        ),
        None,
    )
    if playlist is None or not _same_path(playlist.path, state.playlist_path):
        return ProjectScanIdentityResult(
            None,
            "project.playlist_missing",
            state.playlist_path,
        )
    if (
        int(playlist.duration_90k) != state.playlist_duration_90k
        or playlist.timeline_fingerprint != state.playlist_timeline_fingerprint
    ):
        return ProjectScanIdentityResult(
            None,
            "project.playlist_changed",
            playlist.path,
        )
    return ProjectScanIdentityResult(playlist)


def project_structure_issues(
    project: ProjectSnapshot,
) -> tuple[ApplicationIssue, ...]:
    issues: list[ApplicationIssue] = []
    subtitle_ids = {subtitle.id for subtitle in project.subtitles}
    mapping_ids = {mapping.subtitle_id for mapping in project.mappings}
    if not project.subtitles:
        issues.append(_error("no_subtitles", "project has no subtitles"))
    elif mapping_ids != subtitle_ids or len(project.mappings) != len(project.subtitles):
        issues.append(
            _error(
                "incomplete_mappings",
                "project must contain exactly one mapping for every subtitle",
            )
        )

    boundary_times = {item.id: item.time_90k for item in project.boundaries}
    ordered_mappings = []
    mapping_by_subtitle = {item.subtitle_id: item for item in project.mappings}
    for subtitle in sorted(project.subtitles, key=lambda item: item.order):
        mapping = mapping_by_subtitle.get(subtitle.id)
        if mapping is None:
            continue
        if (
            boundary_times.get(mapping.start_boundary_id) != mapping.start_90k
            or boundary_times.get(mapping.end_boundary_id) != mapping.end_90k
        ):
            issues.append(
                _error(
                    "mapping_boundary_mismatch",
                    (
                        f"mapping for subtitle {subtitle.id!r} disagrees with "
                        "its saved boundaries"
                    ),
                )
            )
        ordered_mappings.append(mapping)
    for previous, current in pairwise(ordered_mappings):
        if previous.end_90k > current.start_90k:
            issues.append(
                _error(
                    "mapping_order_mismatch",
                    "saved mappings overlap or disagree with subtitle order",
                )
            )
            break
    if not project.outputs:
        issues.append(_error("no_outputs", "project has no output targets"))
    return tuple(issues)


def project_source_issues(
    checks: Sequence[SourceCheck],
) -> tuple[ApplicationIssue, ...]:
    return tuple(
        _error(
            f"source_{check.state.value}",
            f"project source is {check.state.value}: {check.path}",
            str(check.path),
        )
        for check in checks
        if check.state is not SourceState.UNCHANGED
    )


def project_subtitle_identity_issues(
    project: ProjectSnapshot,
    state: ProjectState,
    subtitles: LoadSubtitlesResult,
) -> tuple[ApplicationIssue, ...]:
    expected = tuple(sorted(project.subtitles, key=lambda item: item.order))
    resolved = tuple(sorted(state.subtitles, key=lambda item: item.order))
    if len(subtitles.assets) != len(expected) or len(resolved) != len(expected):
        return (
            _error(
                "subtitle_count_mismatch",
                "loaded subtitle count does not match the project snapshot",
            ),
        )
    issues: list[ApplicationIssue] = []
    for snapshot, saved_state, asset in zip(
        expected,
        resolved,
        subtitles.assets,
        strict=True,
    ):
        if not _same_path(saved_state.path, asset.path):
            issues.append(
                _error(
                    "subtitle_path_mismatch",
                    f"loaded subtitle path differs for {snapshot.id!r}",
                    str(asset.path),
                )
            )
        if asset.format.value.casefold() != snapshot.format.casefold():
            issues.append(
                _error(
                    "subtitle_format_mismatch",
                    (
                        f"subtitle {snapshot.id!r} changed from "
                        f"{snapshot.format} to {asset.format.value}"
                    ),
                    str(asset.path),
                )
            )
    return tuple(issues)


def project_additional_boundaries(
    project: ProjectSnapshot,
    playlist: PlaylistInfo,
) -> tuple[TimelineBoundary, ...]:
    automatic = build_playlist_boundaries(playlist)
    additions: list[TimelineBoundary] = []
    used_ids = {item.id for item in automatic}
    by_id = {item.id: item for item in project.boundaries}

    for saved in project.boundaries:
        if not saved.user_created:
            continue
        additions.append(_saved_boundary(saved, used_ids))
        used_ids.add(additions[-1].id)

    available_times = {
        int(item.time_90k) for item in (*automatic, *additions) if item.enabled
    }
    for mapping in project.mappings:
        for boundary_id, time_90k in (
            (mapping.start_boundary_id, mapping.start_90k),
            (mapping.end_boundary_id, mapping.end_90k),
        ):
            if time_90k in available_times:
                continue
            saved_boundary = by_id.get(boundary_id)
            if saved_boundary is None:
                raise ValueError(
                    f"project mapping boundary {boundary_id!r} is missing"
                )
            addition = _saved_boundary(saved_boundary, used_ids)
            additions.append(addition)
            used_ids.add(addition.id)
            available_times.add(time_90k)
    return tuple(additions)


def project_mapping_locks(
    project: ProjectSnapshot,
    playlist: PlaylistInfo,
    additional_boundaries: tuple[TimelineBoundary, ...],
) -> tuple[MappingLock, ...]:
    candidates = (*build_playlist_boundaries(playlist), *additional_boundaries)
    mapping_by_subtitle = {item.subtitle_id: item for item in project.mappings}
    locks: list[MappingLock] = []
    for index, subtitle in enumerate(
        sorted(project.subtitles, key=lambda item: item.order)
    ):
        mapping = mapping_by_subtitle.get(subtitle.id)
        if mapping is None:
            continue
        locks.append(
            MappingLock(
                f"episode-{index + 1}",
                _boundary_id_for_time(
                    candidates,
                    mapping.start_90k,
                    preferred=mapping.start_boundary_id,
                ),
                _boundary_id_for_time(
                    candidates,
                    mapping.end_90k,
                    preferred=mapping.end_boundary_id,
                ),
                MediaTick90k(mapping.manual_offset_90k),
            )
        )
    return tuple(locks)


def project_reproduction_issues(
    project: ProjectSnapshot,
    state: ProjectState,
    prepared: PreparedMerge,
) -> tuple[ApplicationIssue, ...]:
    if prepared.mapping is None:
        return ()
    expected_subtitles = tuple(sorted(project.subtitles, key=lambda item: item.order))
    resolved_subtitles = tuple(sorted(state.subtitles, key=lambda item: item.order))
    expected_by_id = {item.subtitle_id: item for item in project.mappings}
    actual = prepared.mapping.mappings
    if len(actual) != len(expected_subtitles) or len(resolved_subtitles) != len(
        expected_subtitles
    ):
        return (
            _error(
                "mapping_reproduction_failed",
                "solver returned a different number of mappings than the project",
            ),
        )

    issues: list[ApplicationIssue] = []
    for index, (subtitle, resolved, current) in enumerate(
        zip(expected_subtitles, resolved_subtitles, actual, strict=True)
    ):
        expected = expected_by_id[subtitle.id]
        mismatches: list[str] = []
        if current.episode_id != f"episode-{index + 1}":
            mismatches.append("episode order")
        if not _same_path(Path(current.subtitle_ref), resolved.path):
            mismatches.append("subtitle source")
        if int(current.start_boundary.time_90k) != expected.start_90k:
            mismatches.append("start boundary")
        if int(current.end_boundary.time_90k) != expected.end_90k:
            mismatches.append("end boundary")
        if int(current.manual_offset_90k) != expected.manual_offset_90k:
            mismatches.append("manual offset")
        if current.locked is not expected.locked:
            mismatches.append("lock state")
        if mismatches:
            issues.append(
                _error(
                    "mapping_reproduction_failed",
                    f"subtitle {subtitle.id!r} differs in {', '.join(mismatches)}",
                    current.subtitle_ref,
                )
            )
    return tuple(issues)


def project_with_saved_lock_states(
    project: ProjectSnapshot,
    prepared: PreparedMerge,
    *,
    report_target: MergeReportTarget | None,
) -> PreparedMerge:
    """Keep reproduction constraints separate from the saved user lock state."""

    if prepared.mapping is None:
        return prepared
    expected = {
        f"episode-{index + 1}": saved_mapping.locked
        for index, subtitle in enumerate(
            sorted(project.subtitles, key=lambda item: item.order)
        )
        if (saved_mapping := next(
            (
                item
                for item in project.mappings
                if item.subtitle_id == subtitle.id
            ),
            None,
        ))
        is not None
    }
    mappings = tuple(
        replace(item, locked=expected.get(item.episode_id, item.locked))
        for item in prepared.mapping.mappings
    )
    restored_mapping = replace(prepared.mapping, mappings=mappings)
    execution_report = prepared.execution_report
    report_payload = prepared.report_payload
    if execution_report is not None:
        episodes = tuple(
            replace(
                item,
                locked=expected.get(item.episode_id, item.locked),
            )
            for item in execution_report.episodes
        )
        execution_report = replace(execution_report, episodes=episodes)
        if report_target is not None:
            report_payload = execution_report.serialize(report_target.report_format)
    return replace(
        prepared,
        mapping=restored_mapping,
        execution_report=execution_report,
        report_payload=report_payload,
    )


def project_output_targets(
    project: ProjectSnapshot,
    project_file: Path,
) -> tuple[OutputTarget, ...]:
    targets: list[OutputTarget] = []
    for output in project.outputs:
        if output.resolved_path is None:
            raise ValueError(f"output {output.id!r} has no resolved path")
        try:
            collision = CollisionPolicy(output.collision_policy)
        except ValueError as error:
            raise ValueError(
                f"output {output.id!r} has unsupported collision policy "
                f"{output.collision_policy!r}"
            ) from error
        targets.append(
            FullPathOutputTarget(
                output.id,
                collision_policy=collision,
                encoding=output.encoding,
                path=resolve_output_path(
                    output.resolved_path,
                    project_file=project_file,
                ),
            )
        )
    return tuple(targets)


def project_with_loaded_subtitle_metadata(
    project: ProjectSnapshot,
    state: ProjectState,
    subtitles: LoadSubtitlesResult,
) -> ProjectSnapshot:
    paths_by_id = {item.id: item.path for item in state.subtitles}
    assets_by_path = {_path_identity(item.path): item for item in subtitles.assets}
    loaded = []
    for subtitle in project.subtitles:
        path = paths_by_id[subtitle.id]
        asset = assets_by_path[_path_identity(path)]
        warning_messages = tuple(
            issue.message
            for issue in subtitles.issues
            if issue.severity is ApplicationSeverity.WARNING
            and issue.source is not None
            and _same_path(Path(issue.source), asset.path)
        )
        if asset.analysis.duration_estimated:
            warning_messages = (*warning_messages, "duration estimated")
        loaded.append(
            replace(
                subtitle,
                format=asset.format.value,
                encoding=asset.encoding or "binary",
                raw_end_90k=asset.analysis.raw_end_ticks,
                effective_end_90k=asset.analysis.effective_end_ticks,
                event_count=asset.analysis.event_count,
                style_count=asset.analysis.style_count,
                warnings=tuple(
                    dict.fromkeys((*subtitle.warnings, *warning_messages))
                ),
            )
        )
    return replace(project, subtitles=tuple(loaded))


def project_runtime_state(
    restored: RestoredProject,
    prepared: PreparedMerge,
) -> RestoredProject:
    if prepared.mapping is None:
        return restored
    ordered_subtitles = tuple(
        sorted(restored.state.subtitles, key=lambda item: item.order)
    )
    actual_by_id = {
        subtitle.id: current
        for subtitle, current in zip(
            ordered_subtitles,
            prepared.mapping.mappings,
            strict=True,
        )
    }
    mappings = tuple(
        replace(
            saved,
            start_boundary_id=actual_by_id[saved.subtitle_id].start_boundary.id,
            end_boundary_id=actual_by_id[saved.subtitle_id].end_boundary.id,
            start_90k=int(
                actual_by_id[saved.subtitle_id].start_boundary.time_90k
            ),
            end_90k=int(actual_by_id[saved.subtitle_id].end_boundary.time_90k),
            manual_offset_90k=int(
                actual_by_id[saved.subtitle_id].manual_offset_90k
            ),
        )
        for saved in restored.state.mappings
    )
    boundaries = list(restored.state.boundaries)
    known_ids = {item.id for item in boundaries}
    for current in prepared.mapping.mappings:
        for item in (current.start_boundary, current.end_boundary):
            if item.id in known_ids:
                continue
            boundaries.append(_boundary_snapshot(item))
            known_ids.add(item.id)
    state = replace(
        restored.state,
        boundaries=tuple(boundaries),
        mappings=mappings,
    )
    return RestoredProject(state, restored.source_checks)


def _saved_boundary(
    saved: BoundarySnapshot,
    used_ids: set[str],
) -> TimelineBoundary:
    boundary_id = saved.id
    if boundary_id in used_ids:
        boundary_id = f"project:{boundary_id}"
        suffix = 2
        while boundary_id in used_ids:
            boundary_id = f"project:{saved.id}:{suffix}"
            suffix += 1
    return boundary(
        boundary_id,
        saved.time_90k,
        BoundarySource(BoundaryKind.USER, f"project:{saved.id}"),
        confidence=saved.confidence,
        enabled=saved.enabled,
        user_created=True,
        note=saved.note,
    )


def _boundary_id_for_time(
    boundaries: Sequence[TimelineBoundary],
    time_90k: int,
    *,
    preferred: str,
) -> str:
    matches = sorted(
        (item for item in boundaries if int(item.time_90k) == time_90k),
        key=lambda item: (item.id != preferred, item.id),
    )
    if not matches:
        raise ValueError(f"project mapping time {time_90k} has no saved boundary")
    return matches[0].id


def _boundary_snapshot(item: TimelineBoundary) -> BoundarySnapshot:
    return BoundarySnapshot(
        item.id,
        int(item.time_90k),
        tuple(sorted(kind.value for kind in item.kinds)),
        tuple(source.reference for source in item.sources),
        item.confidence,
        item.enabled,
        item.user_created,
        item.note,
    )


def _identity_issue(identity: ProjectScanIdentityResult) -> ApplicationIssue:
    messages = {
        "project.scan_mismatch": "the saved BDMV could not be scanned",
        "project.index_mismatch": "the scanned index.bdmv is not the saved source",
        "project.playlist_missing": "the saved MPLS was not found in the BDMV",
        "project.playlist_changed": "the saved MPLS timeline no longer matches",
    }
    code = identity.error_code or "project.scan_mismatch"
    return _error(
        code,
        messages.get(code, "the project media identity could not be verified"),
        str(identity.error_source) if identity.error_source is not None else None,
    )


def _has_errors(issues: Sequence[ApplicationIssue]) -> bool:
    return any(item.severity is ApplicationSeverity.ERROR for item in issues)


def _error(
    code: str,
    message: str,
    source: str | None = None,
) -> ApplicationIssue:
    return ApplicationIssue(ApplicationSeverity.ERROR, code, message, source)


def _same_path(left: Path, right: Path) -> bool:
    return _path_identity(left) == _path_identity(right)


def _path_identity(path: Path) -> str:
    absolute = str(path.absolute())
    return absolute.casefold() if os.name == "nt" else absolute
