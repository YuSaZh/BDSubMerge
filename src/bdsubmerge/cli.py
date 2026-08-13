"""Non-interactive command-line surface over shared application services."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import redirect_stderr
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum, IntEnum
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
    MergeReportFormat,
    MergeReportTarget,
    PreparedMerge,
    PrepareMergeRequest,
    ProjectRestoreApplicationService,
    ProjectRestoreRequest,
    ScanRequest,
    ScanResult,
    SubtitleApplicationService,
)
from bdsubmerge.domain.models import PlaylistInfo
from bdsubmerge.output import CollisionPolicy
from bdsubmerge.project import (
    ProjectSchemaError,
    ProjectSnapshot,
    SourceState,
    check_project_sources,
    load_project_bytes,
    project_to_data,
)
from bdsubmerge.runtime_logging import (
    configure_runtime_logging,
    record_runtime_event,
    record_runtime_exception,
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
        if name == "merge":
            command.add_argument(
                "--accept-warnings",
                action="store_true",
                help="explicitly accept preflight warnings before writing output",
            )
            command.add_argument(
                "--report",
                type=Path,
                help="atomically write an optional merge report",
            )
            command.add_argument(
                "--report-format",
                choices=tuple(item.value for item in MergeReportFormat),
                default=MergeReportFormat.JSON.value,
            )
            command.add_argument(
                "--report-collision",
                choices=tuple(item.value for item in CollisionPolicy),
                default=CollisionPolicy.ABORT.value,
            )
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
        if isinstance(error.code, int):
            return error.code
        return int(ExitCode.OK if error.code is None else ExitCode.OPERATION_FAILED)
    if arguments.command is None:
        return int(ExitCode.OK)

    if services is None:
        configure_runtime_logging()
    runtime = services or _default_services()
    record_runtime_event("cli_command_started", command=arguments.command)
    try:
        result = _dispatch(arguments, runtime)
    except (OSError, ProjectSchemaError, ValueError) as error:
        record_runtime_exception("cli_command_failed", error, command=arguments.command)
        result = CommandResult(
            arguments.command,
            ExitCode.INPUT_ERROR,
            issues=(CliIssue("error", "invalid_input", str(error)),),
        )
    except Exception as error:
        record_runtime_exception("cli_command_failed", error, command=arguments.command)
        result = CommandResult(
            arguments.command,
            ExitCode.OPERATION_FAILED,
            issues=(CliIssue("error", "operation_failed", str(error)),),
        )
    _render(result, json_output=arguments.json, verbose=arguments.verbose, out=output)
    if not result.ok and not arguments.json:
        for issue in result.issues:
            print(f"{issue.severity}: {issue.code}: {issue.message}", file=error_output)
    record_runtime_event(
        "cli_command_completed",
        command=result.command,
        exit_code=int(result.exit_code),
        issue_codes=tuple(issue.code for issue in result.issues),
    )
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

    report_target = _report_target(arguments) if arguments.command == "merge" else None
    accept_warnings = bool(getattr(arguments, "accept_warnings", False))
    prepared, preparation_issues = _prepare_project(
        project,
        project_path,
        services,
        report_target=report_target,
        accept_low_confidence=accept_warnings,
    )
    if prepared is None:
        return CommandResult(
            arguments.command,
            ExitCode.VALIDATION_FAILED,
            {"source_checks": check_data},
            preparation_issues,
        )
    if arguments.command == "validate":
        issues = _unique_cli_issues(
            (*preparation_issues, *_application_issues(prepared.issues))
        )
        return CommandResult(
            "validate",
            ExitCode.OK if prepared.ready else ExitCode.VALIDATION_FAILED,
            _prepared_data(prepared, check_data, project),
            issues,
        )

    executed = services.merge.execute(
        ExecuteMergeRequest(
            prepared,
            dry_run=bool(arguments.dry_run),
            accept_warnings=accept_warnings,
        )
    )
    issues = _unique_cli_issues(
        (
            *preparation_issues,
            *_application_issues((*prepared.issues, *executed.issues)),
        )
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
    *,
    report_target: MergeReportTarget | None = None,
    accept_low_confidence: bool = False,
) -> tuple[PreparedMerge | None, tuple[CliIssue, ...]]:
    result = ProjectRestoreApplicationService(
        services.bdmv,
        services.subtitles,
        services.merge,
    ).prepare(
        ProjectRestoreRequest(
            project,
            project_path,
            report_target=report_target,
            accept_low_confidence=accept_low_confidence,
        )
    )
    issues = _application_issues(result.issues)
    return (result.prepared, issues) if result.ready else (None, issues)


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
        "execution_report": _json_value(prepared.execution_report),
        "report_outputs": (
            _json_value(prepared.report_preflight.outputs)
            if prepared.report_preflight is not None
            else []
        ),
    }


def _report_target(arguments: argparse.Namespace) -> MergeReportTarget | None:
    path = getattr(arguments, "report", None)
    if path is None:
        return None
    return MergeReportTarget(
        path,
        MergeReportFormat(str(arguments.report_format)),
        CollisionPolicy(str(arguments.report_collision)),
        (Path(arguments.project),),
    )


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


def _unique_cli_issues(issues: Sequence[CliIssue]) -> tuple[CliIssue, ...]:
    return tuple(dict.fromkeys(issues))


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
