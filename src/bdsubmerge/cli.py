"""Non-interactive command-line surface over shared application services."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import redirect_stderr
from dataclasses import asdict, dataclass, is_dataclass, replace
from enum import Enum, IntEnum
from itertools import pairwise
from pathlib import Path
from typing import Protocol, TextIO

from bdsubmerge import __version__
from bdsubmerge.application import (
    ApplicationIssue,
    BdmvApplicationService,
    ExecuteMergeRequest,
    ExecuteMergeResult,
    InspectRequest,
    InspectResult,
    LoadSubtitlesRequest,
    LoadSubtitlesResult,
    MergeApplicationService,
    PreparedMerge,
    PrepareMergeRequest,
    ScanRequest,
    ScanResult,
    SubtitleApplicationService,
    SubtitleInput,
    build_playlist_boundaries,
)
from bdsubmerge.domain.models import PlaylistInfo, PlaylistMarkInfo
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.mapping import MappingLock, TimelineBoundary
from bdsubmerge.merge import MergeOptions
from bdsubmerge.output import CollisionPolicy, FullPathOutputTarget, OutputTarget
from bdsubmerge.project import (
    ProjectSchemaError,
    ProjectSnapshot,
    SourceState,
    check_project_sources,
    load_project_bytes,
    project_to_data,
    resolve_output_path,
    resolve_path,
)


class ExitCode(IntEnum):
    OK = 0
    USAGE = 2
    INPUT_ERROR = 3
    VALIDATION_FAILED = 4
    OPERATION_FAILED = 5


@dataclass(frozen=True, slots=True)
class CliIssue:
    severity: str
    code: str
    message: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class CommandResult:
    command: str
    exit_code: ExitCode
    data: object | None = None
    issues: tuple[CliIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return self.exit_code is ExitCode.OK


class BdmvService(Protocol):
    def scan(self, request: ScanRequest) -> ScanResult: ...

    def inspect(self, request: InspectRequest) -> InspectResult: ...


class SubtitleService(Protocol):
    def load_ordered(self, request: LoadSubtitlesRequest) -> LoadSubtitlesResult: ...


class MergeService(Protocol):
    def prepare(self, request: PrepareMergeRequest) -> PreparedMerge: ...

    def execute(self, request: ExecuteMergeRequest) -> ExecuteMergeResult: ...


@dataclass(frozen=True, slots=True)
class CliServices:
    bdmv: BdmvService
    subtitles: SubtitleService
    merge: MergeService
    read_bytes: Callable[[Path], bytes]


def _add_common_options(parser: argparse.ArgumentParser, *, suppress: bool = False) -> None:
    default = argparse.SUPPRESS if suppress else False
    parser.add_argument("--json", action="store_true", default=default, help="emit JSON")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=default,
        help="perform all checks without writing output",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=default,
        help="include detailed structures and diagnostics",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bdsubmerge")
    parser.add_argument("--version", action="version", version=__version__)
    _add_common_options(parser)
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help="discover and rank MPLS playlists")
    scan.add_argument("path", type=Path)
    scan.add_argument("--max-depth", type=int, default=4)
    scan.add_argument("--subtitle-duration-90k", type=int)
    scan.add_argument("--subtitle-count", type=int)
    _add_common_options(scan, suppress=True)

    inspect = subparsers.add_parser("inspect", help="inspect one MPLS timeline")
    inspect.add_argument("mpls", type=Path)
    inspect.add_argument("--max-depth", type=int, default=4)
    _add_common_options(inspect, suppress=True)

    for name, help_text in (
        ("plan", "show a persisted merge plan"),
        ("validate", "validate project sources and merge preflight"),
        ("merge", "execute a persisted merge plan"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("project", type=Path)
        _add_common_options(command, suppress=True)
    return parser


def _default_services() -> CliServices:
    return CliServices(
        BdmvApplicationService(),
        SubtitleApplicationService(),
        MergeApplicationService(),
        Path.read_bytes,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    services: CliServices | None = None,
) -> int:
    output = stdout or sys.stdout
    error_output = stderr or sys.stderr
    parser = build_parser()
    try:
        with redirect_stderr(error_output):
            arguments = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    if arguments.command is None:
        return int(ExitCode.OK)

    runtime = services or _default_services()
    try:
        result = _dispatch(arguments, runtime)
    except (OSError, ProjectSchemaError, ValueError) as error:
        result = CommandResult(
            arguments.command,
            ExitCode.INPUT_ERROR,
            issues=(CliIssue("error", "invalid_input", str(error)),),
        )
    except Exception as error:
        result = CommandResult(
            arguments.command,
            ExitCode.OPERATION_FAILED,
            issues=(CliIssue("error", "operation_failed", str(error)),),
        )
    _render(result, json_output=arguments.json, verbose=arguments.verbose, out=output)
    if not result.ok and not arguments.json:
        for issue in result.issues:
            print(f"{issue.severity}: {issue.code}: {issue.message}", file=error_output)
    return int(result.exit_code)


def _dispatch(arguments: argparse.Namespace, services: CliServices) -> CommandResult:
    if arguments.command == "scan":
        return _scan(arguments, services)
    if arguments.command == "inspect":
        return _inspect(arguments, services)
    if arguments.command == "plan":
        project = _load_project(arguments.project, services)
        return CommandResult("plan", ExitCode.OK, project_to_data(project))
    if arguments.command in {"validate", "merge"}:
        return _project_operation(arguments, services)
    raise ValueError(f"unsupported command: {arguments.command}")


def _scan(arguments: argparse.Namespace, services: CliServices) -> CommandResult:
    result = services.bdmv.scan(
        ScanRequest(
            arguments.path,
            max_depth=arguments.max_depth,
            subtitle_total_duration_90k=arguments.subtitle_duration_90k,
            subtitle_count=arguments.subtitle_count,
        )
    )
    issues = _application_issues(result.issues)
    exit_code = ExitCode.OK if result.ready else ExitCode.OPERATION_FAILED
    data = {
        "layout": _json_value(result.layout),
        "playlists": [_playlist_summary(item, arguments.verbose) for item in result.playlists],
    }
    return CommandResult("scan", exit_code, data, issues)


def _inspect(arguments: argparse.Namespace, services: CliServices) -> CommandResult:
    scan = services.bdmv.scan(ScanRequest(arguments.mpls, max_depth=arguments.max_depth))
    if not scan.ready:
        return CommandResult(
            "inspect",
            ExitCode.OPERATION_FAILED,
            issues=_application_issues(scan.issues),
        )
    inspected = services.bdmv.inspect(InspectRequest(scan, arguments.mpls.stem))
    issues = _application_issues((*scan.issues, *inspected.issues))
    available = inspected.playlist is not None and inspected.playlist.is_available
    exit_code = ExitCode.OK if available else ExitCode.OPERATION_FAILED
    return CommandResult("inspect", exit_code, _json_value(inspected.playlist), issues)


def _load_project(path: Path, services: CliServices) -> ProjectSnapshot:
    return load_project_bytes(services.read_bytes(path))


def _project_operation(
    arguments: argparse.Namespace,
    services: CliServices,
) -> CommandResult:
    project_path: Path = arguments.project
    project = _load_project(project_path, services)
    checks = check_project_sources(project, project_file=project_path)
    check_data = tuple(
        {"id": check.id, "path": str(check.path), "state": check.state.value}
        for check in checks
    )
    changed = tuple(check for check in checks if check.state is not SourceState.UNCHANGED)
    if changed:
        issues = tuple(
            CliIssue(
                "error",
                f"source_{check.state.value}",
                f"source is {check.state.value}",
                str(check.path),
            )
            for check in changed
        )
        return CommandResult(
            arguments.command,
            ExitCode.VALIDATION_FAILED,
            {"source_checks": check_data},
            issues,
        )

    prepared, preparation_issues = _prepare_project(project, project_path, services)
    if prepared is None:
        return CommandResult(
            arguments.command,
            ExitCode.VALIDATION_FAILED,
            {"source_checks": check_data},
            preparation_issues,
        )
    if arguments.command == "validate":
        issues = (*preparation_issues, *_application_issues(prepared.issues))
        return CommandResult(
            "validate",
            ExitCode.OK if prepared.ready else ExitCode.VALIDATION_FAILED,
            _prepared_data(prepared, check_data, project),
            issues,
        )

    executed = services.merge.execute(
        ExecuteMergeRequest(prepared, dry_run=bool(arguments.dry_run))
    )
    issues = (
        *preparation_issues,
        *_application_issues((*prepared.issues, *executed.issues)),
    )
    data = _prepared_data(prepared, check_data, project)
    data["dry_run"] = executed.dry_run
    data["written_paths"] = (
        [str(path) for path in executed.receipt.paths] if executed.receipt else []
    )
    data["backup_paths"] = (
        [str(path) for path in executed.receipt.backups] if executed.receipt else []
    )
    return CommandResult(
        "merge",
        ExitCode.OK if executed.succeeded else ExitCode.OPERATION_FAILED,
        data,
        issues,
    )


def _prepare_project(
    project: ProjectSnapshot,
    project_path: Path,
    services: CliServices,
) -> tuple[PreparedMerge | None, tuple[CliIssue, ...]]:
    structure_issues = _project_structure_issues(project)
    if structure_issues:
        return None, structure_issues
    bdmv_path = resolve_path(project.bdmv_path, project_file=project_path)
    scan = services.bdmv.scan(ScanRequest(bdmv_path))
    if not scan.ready or scan.layout is None:
        return None, _application_issues(scan.issues)
    inspected = services.bdmv.inspect(InspectRequest(scan, project.playlist.stem))
    playlist = inspected.playlist
    if playlist is None:
        return None, _application_issues(inspected.issues)
    if (
        playlist.timeline_fingerprint != project.playlist.timeline_fingerprint
        or int(playlist.duration_90k) != project.playlist.duration_90k
    ):
        return None, (
            CliIssue(
                "error",
                "playlist_changed",
                "the scanned playlist timeline no longer matches the project snapshot",
                str(playlist.path),
            ),
        )

    ordered_subtitles = tuple(sorted(project.subtitles, key=lambda item: item.order))
    subtitle_inputs = tuple(
        SubtitleInput(
            resolve_path(item.source.path, project_file=project_path),
            item.encoding or None,
        )
        for item in ordered_subtitles
    )
    subtitles = services.subtitles.load_ordered(LoadSubtitlesRequest(subtitle_inputs))
    if not subtitles.ready:
        return None, _application_issues(subtitles.issues)
    playlist = _playlist_with_project_boundaries(project, playlist)
    output_targets = _output_targets(project, project_path)
    locks = _mapping_locks(project, playlist)
    policy = project.conflict_policy
    prepared = services.merge.prepare(
        PrepareMergeRequest(
            scan.layout,
            playlist,
            subtitles,
            output_targets,
            locks=locks,
            merge_options=MergeOptions(
                playlist_end_ticks=project.playlist.duration_90k,
                accept_script_info_conflicts=policy.accept_script_info_conflicts,
                keep_events_ending_before_zero=policy.keep_events_ending_before_zero,
                clip_negative_starts=policy.clip_negative_starts,
            ),
            accept_low_confidence=True,
        )
    )
    reproduction_issues = _reproduction_issues(
        project,
        project_path,
        prepared,
    )
    preliminary = _application_issues((*scan.issues, *inspected.issues, *subtitles.issues))
    if reproduction_issues:
        return None, (*preliminary, *reproduction_issues)
    return prepared, preliminary


def _project_structure_issues(project: ProjectSnapshot) -> tuple[CliIssue, ...]:
    issues: list[CliIssue] = []
    subtitle_ids = {subtitle.id for subtitle in project.subtitles}
    mapping_ids = {mapping.subtitle_id for mapping in project.mappings}
    if not project.subtitles:
        issues.append(CliIssue("error", "no_subtitles", "project has no subtitles"))
    elif mapping_ids != subtitle_ids or len(project.mappings) != len(project.subtitles):
        issues.append(
            CliIssue(
                "error",
                "incomplete_mappings",
                "project must contain exactly one mapping for every subtitle",
            )
        )
    boundary_times = {boundary.id: boundary.time_90k for boundary in project.boundaries}
    ordered_mappings = []
    mapping_by_subtitle = {mapping.subtitle_id: mapping for mapping in project.mappings}
    for subtitle in sorted(project.subtitles, key=lambda item: item.order):
        mapping = mapping_by_subtitle.get(subtitle.id)
        if mapping is None:
            continue
        if (
            boundary_times.get(mapping.start_boundary_id) != mapping.start_90k
            or boundary_times.get(mapping.end_boundary_id) != mapping.end_90k
        ):
            issues.append(
                CliIssue(
                    "error",
                    "mapping_boundary_mismatch",
                    f"mapping for subtitle {subtitle.id!r} disagrees with its saved boundaries",
                )
            )
        ordered_mappings.append(mapping)
    for previous, current in pairwise(ordered_mappings):
        if previous.end_90k > current.start_90k:
            issues.append(
                CliIssue(
                    "error",
                    "mapping_order_mismatch",
                    "saved mappings overlap or disagree with subtitle order",
                )
            )
            break
    orders = tuple(subtitle.order for subtitle in project.subtitles)
    if len(set(orders)) != len(orders):
        issues.append(CliIssue("error", "duplicate_order", "subtitle order values must be unique"))
    if not project.outputs:
        issues.append(CliIssue("error", "no_outputs", "project has no output targets"))
    return tuple(issues)


def _playlist_with_project_boundaries(
    project: ProjectSnapshot,
    playlist: PlaylistInfo,
) -> PlaylistInfo:
    """Add exact saved mapping times that are absent from the scanned candidates."""
    runtime = build_playlist_boundaries(playlist)
    available_times = {int(item.time_90k) for item in runtime}
    required_times = {
        time
        for mapping in project.mappings
        for time in (mapping.start_90k, mapping.end_90k)
    }
    missing_times = sorted(required_times - available_times)
    if not missing_times:
        return playlist
    next_index = max((mark.index for mark in playlist.marks), default=-1) + 1
    injected = tuple(
        _project_boundary_mark(playlist, next_index + offset, time_90k)
        for offset, time_90k in enumerate(missing_times)
    )
    return replace(playlist, marks=(*playlist.marks, *injected))


def _project_boundary_mark(
    playlist: PlaylistInfo,
    index: int,
    time_90k: int,
) -> PlaylistMarkInfo:
    for item in playlist.play_items:
        if int(item.logical_start_90k) <= time_90k <= int(item.logical_end_90k):
            relative_90k = time_90k - int(item.logical_start_90k)
            return PlaylistMarkInfo(
                index=index,
                mark_type=0xFF,
                play_item_index=item.index,
                timestamp_45k=item.in_time_45k + relative_90k // 2,
                time_90k=MediaTick90k(time_90k),
            )
    raise ValueError(f"saved mapping time {time_90k} is outside the playlist timeline")


def _reproduction_issues(
    project: ProjectSnapshot,
    project_path: Path,
    prepared: PreparedMerge,
) -> tuple[CliIssue, ...]:
    if prepared.mapping is None:
        return ()
    expected_subtitles = tuple(sorted(project.subtitles, key=lambda item: item.order))
    expected_by_id = {mapping.subtitle_id: mapping for mapping in project.mappings}
    actual = prepared.mapping.mappings
    if len(actual) != len(expected_subtitles):
        return (
            CliIssue(
                "error",
                "mapping_reproduction_failed",
                "solver returned a different number of mappings than the project snapshot",
            ),
        )
    issues: list[CliIssue] = []
    for index, (subtitle, current) in enumerate(zip(expected_subtitles, actual, strict=True)):
        expected = expected_by_id[subtitle.id]
        expected_path = resolve_path(subtitle.source.path, project_file=project_path)
        mismatches: list[str] = []
        if current.episode_id != f"episode-{index + 1}":
            mismatches.append("episode order")
        if Path(current.subtitle_ref) != expected_path:
            mismatches.append("subtitle source")
        if int(current.start_boundary.time_90k) != expected.start_90k:
            mismatches.append("start boundary")
        if int(current.end_boundary.time_90k) != expected.end_90k:
            mismatches.append("end boundary")
        if int(current.manual_offset_90k) != expected.manual_offset_90k:
            mismatches.append("manual offset")
        if not current.locked:
            mismatches.append("lock state")
        if mismatches:
            issues.append(
                CliIssue(
                    "error",
                    "mapping_reproduction_failed",
                    f"subtitle {subtitle.id!r} differs in {', '.join(mismatches)}",
                    str(expected_path),
                )
            )
    return tuple(issues)


def _mapping_locks(
    project: ProjectSnapshot,
    playlist: PlaylistInfo,
) -> tuple[MappingLock, ...]:
    runtime_boundaries = build_playlist_boundaries(playlist)
    mapping_by_subtitle = {item.subtitle_id: item for item in project.mappings}
    locks: list[MappingLock] = []
    for index, subtitle in enumerate(sorted(project.subtitles, key=lambda item: item.order)):
        mapping = mapping_by_subtitle.get(subtitle.id)
        if mapping is None:
            continue
        start_id = _boundary_id_for_time(runtime_boundaries, mapping.start_90k)
        end_id = _boundary_id_for_time(runtime_boundaries, mapping.end_90k)
        locks.append(
            MappingLock(
                f"episode-{index + 1}",
                start_id,
                end_id,
                MediaTick90k(mapping.manual_offset_90k),
            )
        )
    return tuple(locks)


def _boundary_id_for_time(
    boundaries: Sequence[TimelineBoundary],
    time_90k: int,
) -> str:
    matches = sorted(
        boundary.id
        for boundary in boundaries
        if int(boundary.time_90k) == time_90k
    )
    if not matches:
        raise ValueError(f"project mapping time {time_90k} has no saved boundary")
    return matches[0]


def _output_targets(
    project: ProjectSnapshot,
    project_path: Path,
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
                path=resolve_output_path(output.resolved_path, project_file=project_path),
            )
        )
    return tuple(targets)


def _prepared_data(
    prepared: PreparedMerge,
    source_checks: object,
    project: ProjectSnapshot,
) -> dict[str, object]:
    preflight = prepared.output_preflight
    stored_presets = {output.id: output.preset for output in project.outputs}
    outputs: list[object] = []
    if preflight:
        for output in preflight.outputs:
            value = _json_value(output)
            if isinstance(value, dict):
                value["stored_preset"] = stored_presets.get(output.target_id, "")
            outputs.append(value)
    return {
        "ready": prepared.ready,
        "source_checks": source_checks,
        "outputs": outputs,
        "mapping": _json_value(prepared.mapping),
        "report": _json_value(prepared.report),
    }


def _playlist_summary(playlist: PlaylistInfo, verbose: bool) -> dict[str, object]:
    summary: dict[str, object] = {
        "path": str(playlist.path),
        "stem": playlist.stem,
        "duration_90k": int(playlist.duration_90k),
        "play_item_count": len(playlist.play_items),
        "mark_count": len(playlist.marks),
        "unique_clip_count": playlist.unique_clip_count,
        "repeated_clip_count": playlist.repeated_clip_count,
        "has_multi_angle": playlist.has_multi_angle,
        "references_complete": playlist.references_complete,
        "score": playlist.score,
        "confidence": playlist.confidence.value,
        "available": playlist.is_available,
        "reasons": list(playlist.recommendation_reasons),
    }
    if verbose:
        summary["play_items"] = _json_value(playlist.play_items)
        summary["marks"] = _json_value(playlist.marks)
        summary["warnings"] = list(playlist.warnings)
        summary["errors"] = list(playlist.errors)
        summary["timeline_fingerprint"] = _json_value(playlist.timeline_fingerprint)
    return summary


def _application_issues(issues: Sequence[ApplicationIssue]) -> tuple[CliIssue, ...]:
    return tuple(
        CliIssue(issue.severity.value, issue.code, issue.message, issue.source)
        for issue in issues
    )


def _json_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_value(item) for item in value]
    return str(value)


def _render(result: CommandResult, *, json_output: bool, verbose: bool, out: TextIO) -> None:
    envelope = {
        "ok": result.ok,
        "command": result.command,
        "exit_code": int(result.exit_code),
        "data": _json_value(result.data),
        "issues": _json_value(result.issues),
    }
    if json_output:
        print(json.dumps(envelope, ensure_ascii=False, sort_keys=True), file=out)
        return
    print(f"{result.command}: {'ok' if result.ok else 'failed'}", file=out)
    if result.data is not None:
        if verbose:
            print(json.dumps(_json_value(result.data), ensure_ascii=False, indent=2), file=out)
        elif isinstance(result.data, Mapping):
            _render_summary(result.data, out)


def _render_summary(data: Mapping[object, object], out: TextIO) -> None:
    playlists = data.get("playlists")
    if isinstance(playlists, list):
        for item in playlists:
            if isinstance(item, Mapping):
                print(
                    f"{item.get('stem', '')}: {item.get('duration_90k', 0)} ticks "
                    f"score={item.get('score', 0)}",
                    file=out,
                )
    outputs = data.get("outputs")
    if isinstance(outputs, list):
        for output in outputs:
            if isinstance(output, Mapping):
                print(str(output.get("path", "")), file=out)


if __name__ == "__main__":
    raise SystemExit(main())
