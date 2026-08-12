from __future__ import annotations

import json
from dataclasses import dataclass, replace
from io import StringIO
from pathlib import Path

import pytest

import bdsubmerge.cli as cli_module
from bdsubmerge.application import (
    InspectRequest,
    InspectResult,
    MergeApplicationService,
    ScanRequest,
    ScanResult,
    SubtitleApplicationService,
)
from bdsubmerge.cli import CliServices, ExitCode, build_parser, main
from bdsubmerge.domain.models import (
    BdmvLayout,
    PlayItemInfo,
    PlaylistConfidence,
    PlaylistInfo,
    ReferenceStatus,
)
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.mapping import EpisodeRequest, auto_map_episodes
from bdsubmerge.output import (
    CollisionPolicy,
    OutputPreset,
    PreflightResult,
    ResolvedOutput,
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


def _playlist_with_item(path: Path) -> PlaylistInfo:
    item = PlayItemInfo(
        0,
        "00001",
        "M2TS",
        0,
        50,
        MediaTick90k(0),
        MediaTick90k(100),
        0,
        False,
        0,
        1,
        ReferenceStatus(True, True),
    )
    return PlaylistInfo(
        path / "BDMV" / "PLAYLIST" / "00001.mpls",
        "00001",
        MediaTick90k(100),
        (item,),
        (),
        timeline_fingerprint=(("00001", 0, 50, 0),),
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


def test_saved_non_candidate_boundaries_become_exact_ordered_solver_locks(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    playlist = cli_module._playlist_with_project_boundaries(
        project,
        _playlist_with_item(tmp_path),
    )
    boundaries = cli_module.build_playlist_boundaries(playlist)
    locks = cli_module._mapping_locks(project, playlist)
    result = auto_map_episodes(
        (
            EpisodeRequest("episode-1", MediaTick90k(30), str(tmp_path / "01.ass")),
            EpisodeRequest("episode-2", MediaTick90k(40), str(tmp_path / "02.ass")),
        ),
        boundaries,
        locks=locks,
    )
    assert [
        (
            int(mapping.start_boundary.time_90k),
            int(mapping.end_boundary.time_90k),
            int(mapping.manual_offset_90k),
            mapping.locked,
        )
        for mapping in result.mappings
    ] == [(10, 40, 7, True), (50, 90, -3, True)]

    prepared = cli_module.PreparedMerge(result, None, None, None, ())
    assert cli_module._reproduction_issues(project, tmp_path / "show.bdsm.json", prepared) == ()
    changed_mapping = replace(result.mappings[0], manual_offset_90k=MediaTick90k(8))
    changed_result = replace(result, mappings=(changed_mapping, result.mappings[1]))
    changed = cli_module.PreparedMerge(changed_result, None, None, None, ())
    issues = cli_module._reproduction_issues(project, tmp_path / "show.bdsm.json", changed)
    assert issues[0].code == "mapping_reproduction_failed"
    assert "manual offset" in issues[0].message


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
