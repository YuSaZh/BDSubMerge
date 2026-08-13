from __future__ import annotations

import json
from dataclasses import dataclass, replace
from io import StringIO
from pathlib import Path

import pytest

import bdsubmerge.cli as cli_module
from bdsubmerge.application import (
    ApplicationIssue,
    ApplicationSeverity,
    ExecuteMergeRequest,
    ExecuteMergeResult,
    InspectRequest,
    InspectResult,
    MergeApplicationService,
    MergeReportFormat,
    PreparedMerge,
    PrepareMergeRequest,
    ScanRequest,
    ScanResult,
    SubtitleApplicationService,
)
from bdsubmerge.cli import CliIssue, CliServices, ExitCode, build_parser, main
from bdsubmerge.domain.models import BdmvLayout, PlaylistConfidence, PlaylistInfo
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.output import (
    CollisionPolicy,
    OutputPreset,
    PreflightResult,
    ResolvedOutput,
    WriteReceipt,
)
from bdsubmerge.project import (
    BoundarySnapshot,
    FileFingerprint,
    FileSnapshot,
    MappingSnapshot,
    OutputSnapshot,
    PlaylistSnapshot,
    ProjectSnapshot,
    StoredPath,
    SubtitleSnapshot,
)


def _layout(path: Path) -> BdmvLayout:
    bdmv = path / "BDMV"
    return BdmvLayout(
        path,
        path,
        bdmv,
        bdmv / "index.bdmv",
        bdmv / "PLAYLIST",
        bdmv / "CLIPINF",
        bdmv / "STREAM",
    )


def _playlist(path: Path) -> PlaylistInfo:
    return PlaylistInfo(
        path / "BDMV" / "PLAYLIST" / "00001.mpls",
        "00001",
        MediaTick90k(90_000),
        (),
        (),
        score=73,
        confidence=PlaylistConfidence.MEDIUM,
    )


def _project(path: Path) -> ProjectSnapshot:
    def stored(value: Path) -> StoredPath:
        return StoredPath(None, str(value))

    def snapshot(value: Path) -> FileSnapshot:
        return FileSnapshot(stored(value), FileFingerprint(0, 0))

    return ProjectSnapshot(
        snapshot(path / "BDMV"),
        snapshot(path / "BDMV" / "index.bdmv"),
        PlaylistSnapshot(
            snapshot(path / "BDMV" / "PLAYLIST" / "00001.mpls"),
            "00001",
            100,
            (("00001", 0, 50, 0),),
        ),
        (
            SubtitleSnapshot("second", snapshot(path / "02.ass"), "ass", "utf-8", 1),
            SubtitleSnapshot("first", snapshot(path / "01.ass"), "ass", "utf-8", 0),
        ),
        (
            BoundarySnapshot("saved-10", 10),
            BoundarySnapshot("saved-40", 40),
            BoundarySnapshot("saved-50", 50),
            BoundarySnapshot("saved-90", 90),
        ),
        (
            MappingSnapshot("second", "saved-50", "saved-90", 50, 90, -3, True, "high"),
            MappingSnapshot("first", "saved-10", "saved-40", 10, 40, 7, True, "high"),
        ),
        (
            OutputSnapshot(
                "primary",
                "jriver",
                "",
                stored(path / "BDMV" / "index.ass"),
                "utf-8-sig",
                "abort",
            ),
        ),
    )


@dataclass
class FakeBdmvService:
    root: Path
    last_scan: ScanRequest | None = None

    def scan(self, request: ScanRequest) -> ScanResult:
        self.last_scan = request
        return ScanResult(_layout(self.root), (_playlist(self.root),))

    def inspect(self, request: InspectRequest) -> InspectResult:
        playlist = next(
            (item for item in request.scan.playlists if item.stem == request.playlist_stem),
            None,
        )
        return InspectResult(playlist)


def _services(
    root: Path,
    bdmv: FakeBdmvService | None = None,
    data: bytes = b"",
) -> CliServices:
    return CliServices(
        bdmv or FakeBdmvService(root),
        SubtitleApplicationService(read_bytes=lambda _: b""),
        MergeApplicationService(),
        lambda _: data,
    )


def test_parser_defines_every_required_command_and_postfix_common_flags() -> None:
    parser = build_parser()
    for command, argument in (
        ("scan", "disc"),
        ("inspect", "00001.mpls"),
        ("plan", "show.bdsm.json"),
        ("validate", "show.bdsm.json"),
        ("merge", "show.bdsm.json"),
    ):
        parsed = parser.parse_args((command, argument, "--json", "--dry-run", "--verbose"))
        assert parsed.command == command
        assert parsed.json is True
        assert parsed.dry_run is True
        assert parsed.verbose is True


@pytest.mark.parametrize("accepted", (False, True))
def test_merge_accept_warnings_flag_reaches_shared_execute_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    accepted: bool,
) -> None:
    project = _project(tmp_path)
    prepared = PreparedMerge(None, None, None, None, ())

    @dataclass
    class CapturingMergeService:
        requests: list[ExecuteMergeRequest]

        def prepare(self, request: PrepareMergeRequest) -> PreparedMerge:
            raise AssertionError(f"unexpected prepare request: {request}")

        def execute(self, request: ExecuteMergeRequest) -> ExecuteMergeResult:
            self.requests.append(request)
            return ExecuteMergeResult(prepared, False, WriteReceipt((), ()))

    merge = CapturingMergeService([])
    services = replace(_services(tmp_path), merge=merge)
    preparation_acceptance: list[bool] = []

    def prepare_project(
        *args: object,
        **kwargs: object,
    ) -> tuple[PreparedMerge, tuple[CliIssue, ...]]:
        del args
        preparation_acceptance.append(bool(kwargs["accept_low_confidence"]))
        return prepared, ()

    monkeypatch.setattr(cli_module, "_load_project", lambda *args: project)
    monkeypatch.setattr(cli_module, "check_project_sources", lambda *args, **kwargs: ())
    monkeypatch.setattr(cli_module, "_prepare_project", prepare_project)
    arguments = ["merge", str(tmp_path / "show.bdsm.json")]
    if accepted:
        arguments.append("--accept-warnings")

    result = cli_module._project_operation(build_parser().parse_args(arguments), services)

    assert result.exit_code is ExitCode.OK
    assert preparation_acceptance == [accepted]
    assert len(merge.requests) == 1
    assert merge.requests[0].accept_warnings is accepted


@pytest.mark.parametrize(
    "arguments",
    (("validate", "show.bdsm.json"), ("merge", "show.bdsm.json", "--dry-run")),
)
def test_project_operations_report_shared_preflight_issues_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arguments: tuple[str, ...],
) -> None:
    project = _project(tmp_path)
    application_issue = ApplicationIssue(
        ApplicationSeverity.WARNING,
        "playlist_warning",
        "selected playlist requires review",
        "00001.mpls",
    )
    cli_issue = CliIssue(
        "warning",
        application_issue.code,
        application_issue.message,
        application_issue.source,
    )
    prepared = PreparedMerge(None, None, None, None, (application_issue,))

    monkeypatch.setattr(cli_module, "_load_project", lambda *args: project)
    monkeypatch.setattr(cli_module, "check_project_sources", lambda *args, **kwargs: ())
    monkeypatch.setattr(
        cli_module,
        "_prepare_project",
        lambda *args, **kwargs: (prepared, (cli_issue,)),
    )

    result = cli_module._project_operation(
        build_parser().parse_args(arguments),
        _services(tmp_path),
    )

    assert [issue for issue in result.issues if issue == cli_issue] == [cli_issue]


def test_scan_json_has_stable_envelope_and_uses_application_request(tmp_path: Path) -> None:
    fake = FakeBdmvService(tmp_path)
    stdout = StringIO()
    code = main(
        (
            "scan",
            str(tmp_path),
            "--max-depth",
            "2",
            "--subtitle-duration-90k",
            "90000",
            "--subtitle-count",
            "1",
            "--json",
        ),
        stdout=stdout,
        services=_services(tmp_path, fake),
    )
    payload = json.loads(stdout.getvalue())
    assert code == ExitCode.OK
    assert payload["ok"] is True
    assert payload["command"] == "scan"
    assert payload["data"]["playlists"][0]["stem"] == "00001"
    assert fake.last_scan == ScanRequest(tmp_path, 2, 90_000, 1)


def test_invalid_project_json_is_a_structured_input_error(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    code = main(
        ("plan", str(tmp_path / "bad.bdsm.json"), "--json"),
        stdout=stdout,
        stderr=stderr,
        services=_services(tmp_path, data=b"not json"),
    )
    payload = json.loads(stdout.getvalue())
    assert code == ExitCode.INPUT_ERROR
    assert payload["issues"][0]["code"] == "invalid_input"
    assert stderr.getvalue() == ""


def test_empty_arguments_remain_a_successful_no_op() -> None:
    assert main((), stdout=StringIO(), stderr=StringIO()) == ExitCode.OK


def test_argparse_usage_error_uses_injected_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    injected = StringIO()
    assert main(("scan",), stdout=StringIO(), stderr=injected) == ExitCode.USAGE
    captured = capsys.readouterr()
    assert "required" in injected.getvalue()
    assert captured.err == ""


def test_prepared_output_reports_original_stored_preset(tmp_path: Path) -> None:
    project = _project(tmp_path)
    resolved = ResolvedOutput(
        "primary",
        OutputPreset.FULL_PATH,
        tmp_path / "BDMV" / "index.ass",
        "utf-8-sig",
        CollisionPolicy.ABORT,
    )
    prepared = cli_module.PreparedMerge(
        None,
        PreflightResult((resolved,), ()),
        None,
        None,
        (),
    )
    data = cli_module._prepared_data(prepared, (), project)
    outputs = data["outputs"]
    assert isinstance(outputs, list)
    assert isinstance(outputs[0], dict)
    assert outputs[0]["preset"] == "full_path"
    assert outputs[0]["stored_preset"] == "jriver"


def test_merge_report_flags_create_a_project_protected_target(tmp_path: Path) -> None:
    project_path = tmp_path / "show.bdsm.json"
    report_path = tmp_path / "merge-report.txt"
    arguments = build_parser().parse_args(
        (
            "merge",
            str(project_path),
            "--report",
            str(report_path),
            "--report-format",
            "text",
            "--report-collision",
            "backup",
        )
    )

    target = cli_module._report_target(arguments)

    assert target is not None
    assert target.path == report_path
    assert target.report_format is MergeReportFormat.TEXT
    assert target.collision_policy is CollisionPolicy.BACKUP
    assert target.protected_paths == (project_path,)
