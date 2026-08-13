from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from bdsubmerge.application import (
    ApplicationIssue,
    ApplicationSeverity,
    LoadSubtitlesRequest,
    LoadSubtitlesResult,
    PreparedMerge,
    PrepareMergeRequest,
    ProjectRestoreApplicationService,
    ProjectRestoreRequest,
    ProjectRestoreResult,
    ScanRequest,
    ScanResult,
    SubtitleAsset,
    build_playlist_boundaries,
    verify_project_scan_identity,
)
from bdsubmerge.domain.models import (
    BdmvLayout,
    PlayItemInfo,
    PlaylistInfo,
    ReferenceStatus,
)
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.mapping import (
    EpisodeMapping,
    MappingConfidence,
    MappingResult,
)
from bdsubmerge.output import CollisionPolicy, FullPathOutputTarget
from bdsubmerge.project import (
    BoundarySnapshot,
    ConflictPolicySnapshot,
    MappingSnapshot,
    OutputSnapshot,
    PlaylistSnapshot,
    ProjectSnapshot,
    ProjectState,
    SourceState,
    SubtitleSnapshot,
    snapshot_file,
    store_path,
)
from bdsubmerge.subtitles import SubtitleFormat, TextSubtitleInfo, parse_ass


@dataclass(slots=True)
class FakeBdmvService:
    result: ScanResult
    requests: list[ScanRequest] = field(default_factory=list)

    def scan(self, request: ScanRequest) -> ScanResult:
        self.requests.append(request)
        return self.result


@dataclass(slots=True)
class FakeSubtitleService:
    result: LoadSubtitlesResult
    requests: list[LoadSubtitlesRequest] = field(default_factory=list)
    after_load: Callable[[], None] | None = None

    def load_ordered(self, request: LoadSubtitlesRequest) -> LoadSubtitlesResult:
        self.requests.append(request)
        if self.after_load is not None:
            self.after_load()
        return self.result


@dataclass(slots=True)
class FakeMergeService:
    requests: list[PrepareMergeRequest] = field(default_factory=list)
    mapping_transform: Callable[[MappingResult], MappingResult] | None = None
    issues: tuple[ApplicationIssue, ...] = ()
    omit_mapping: bool = False

    def prepare(self, request: PrepareMergeRequest) -> PreparedMerge:
        self.requests.append(request)
        boundaries = {
            item.id: item
            for item in (
                *build_playlist_boundaries(request.playlist),
                *request.additional_boundaries,
            )
        }
        mappings = tuple(
            EpisodeMapping(
                lock.episode_id,
                str(request.subtitles.assets[index].path),
                boundaries[lock.start_boundary_id],
                boundaries[lock.end_boundary_id],
                lock.manual_offset_90k,
                100,
                MappingConfidence.HIGH,
                locked=True,
            )
            for index, lock in enumerate(request.locks)
        )
        mapping = MappingResult(mappings, 0, MappingConfidence.HIGH)
        if self.mapping_transform is not None:
            mapping = self.mapping_transform(mapping)
        return PreparedMerge(
            None if self.omit_mapping else mapping,
            None,
            None,
            None,
            self.issues,
        )


@dataclass(frozen=True, slots=True)
class ProjectFixture:
    root: Path
    project_file: Path
    bdmv: Path
    index: Path
    playlist_path: Path
    subtitle_paths: tuple[Path, Path]
    output_path: Path
    project: ProjectSnapshot
    scan: ScanResult
    subtitles: LoadSubtitlesResult


def _make_fixture(tmp_path: Path) -> ProjectFixture:
    root = tmp_path / "Show"
    bdmv = root / "BDMV"
    playlist_directory = bdmv / "PLAYLIST"
    playlist_directory.mkdir(parents=True)
    (bdmv / "CLIPINF").mkdir()
    (bdmv / "STREAM").mkdir()
    index = bdmv / "index.bdmv"
    playlist_path = playlist_directory / "00001.mpls"
    first_subtitle = root / "01.ass"
    second_subtitle = root / "02.ass"
    index.write_bytes(b"index")
    playlist_path.write_bytes(b"playlist")
    first_subtitle.write_text("first", encoding="utf-8")
    second_subtitle.write_text("second", encoding="utf-8")

    project_file = root / "show.bdsm.json"
    output_path = root / "exports" / "merged.ass"
    fingerprint = (
        ("00001", 0, 45_000, 0),
        ("00002", 0, 45_000, 0),
    )
    playlist = PlaylistInfo(
        playlist_path,
        "00001",
        MediaTick90k(180_000),
        (
            _play_item(0, "00001", 0, 90_000),
            _play_item(1, "00002", 90_000, 180_000),
        ),
        (),
        timeline_fingerprint=fingerprint,
    )
    layout = BdmvLayout(
        root,
        root,
        bdmv,
        index,
        playlist_directory,
        bdmv / "CLIPINF",
        bdmv / "STREAM",
    )
    conflict_policy = ConflictPolicySnapshot(
        accept_script_info_conflicts=True,
        keep_events_ending_before_zero=True,
        clip_negative_starts=False,
        preserve_unknown_sections=False,
    )
    project = ProjectSnapshot(
        snapshot_file(bdmv, project_file=project_file),
        snapshot_file(index, project_file=project_file),
        PlaylistSnapshot(
            snapshot_file(playlist_path, project_file=project_file),
            playlist.stem,
            int(playlist.duration_90k),
            playlist.timeline_fingerprint,
        ),
        (
            SubtitleSnapshot(
                "first",
                snapshot_file(first_subtitle, project_file=project_file),
                "ass",
                "utf-8",
                0,
            ),
            SubtitleSnapshot(
                "second",
                snapshot_file(second_subtitle, project_file=project_file),
                "ass",
                "utf-8",
                1,
            ),
        ),
        (
            BoundarySnapshot("saved-start", 0),
            BoundarySnapshot("saved-middle", 90_000),
            BoundarySnapshot("saved-end", 180_000),
        ),
        (
            MappingSnapshot(
                "first",
                "saved-start",
                "saved-middle",
                0,
                90_000,
                900,
                True,
                "high",
            ),
            MappingSnapshot(
                "second",
                "saved-middle",
                "saved-end",
                90_000,
                180_000,
                0,
                False,
                "medium",
            ),
        ),
        (
            OutputSnapshot(
                "primary",
                "jriver",
                "legacy-{playlist}",
                store_path(output_path, project_file=project_file),
                "utf-8-sig",
                CollisionPolicy.AUTO_RENAME.value,
                "backup",
            ),
        ),
        conflict_policy,
        "saved note",
    )
    subtitles = LoadSubtitlesResult(
        (
            _subtitle_asset(first_subtitle, raw_end=100_000, effective_end=90_000),
            _subtitle_asset(
                second_subtitle,
                raw_end=120_000,
                effective_end=90_000,
                estimated=True,
            ),
        ),
        SubtitleFormat.ASS,
    )
    return ProjectFixture(
        root,
        project_file,
        bdmv,
        index,
        playlist_path,
        (first_subtitle, second_subtitle),
        output_path,
        project,
        ScanResult(layout, (playlist,)),
        subtitles,
    )


def _play_item(index: int, clip_id: str, start: int, end: int) -> PlayItemInfo:
    return PlayItemInfo(
        index,
        clip_id,
        "M2TS",
        start // 2,
        end // 2,
        MediaTick90k(start),
        MediaTick90k(end),
        0,
        False,
        0,
        1,
        ReferenceStatus(True, True),
    )


def _subtitle_asset(
    path: Path,
    *,
    raw_end: int,
    effective_end: int,
    estimated: bool = False,
) -> SubtitleAsset:
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
    )
    return SubtitleAsset(
        path,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(
            3,
            2,
            0,
            raw_end,
            effective_end,
            False,
            1920,
            1080,
            estimated,
        ),
        "utf-8",
    )


def _prepare(
    fixture: ProjectFixture,
    *,
    project: ProjectSnapshot | None = None,
    scan: ScanResult | None = None,
    subtitles: LoadSubtitlesResult | None = None,
    after_load: Callable[[], None] | None = None,
    mapping_transform: Callable[[MappingResult], MappingResult] | None = None,
    merge_issues: tuple[ApplicationIssue, ...] = (),
    omit_mapping: bool = False,
) -> tuple[
    ProjectRestoreResult,
    FakeBdmvService,
    FakeSubtitleService,
    FakeMergeService,
]:
    bdmv_service = FakeBdmvService(scan or fixture.scan)
    subtitle_service = FakeSubtitleService(
        subtitles or fixture.subtitles,
        after_load=after_load,
    )
    merge_service = FakeMergeService(
        mapping_transform=mapping_transform,
        issues=merge_issues,
        omit_mapping=omit_mapping,
    )
    result = ProjectRestoreApplicationService(
        bdmv_service,
        subtitle_service,
        merge_service,
    ).prepare(
        ProjectRestoreRequest(project or fixture.project, fixture.project_file)
    )
    return result, bdmv_service, subtitle_service, merge_service


def _issue_codes(result: ProjectRestoreResult) -> set[str]:
    return {issue.code for issue in result.issues}


def _state(root: Path) -> ProjectState:
    bdmv = root / "BDMV"
    return ProjectState(
        bdmv,
        bdmv / "index.bdmv",
        bdmv / "PLAYLIST" / "00001.mpls",
        "00001",
        90_000,
        (("00001", 0, 45_000, 0),),
        (),
        (),
        (),
        (),
    )


def _identity_scan(root: Path) -> ScanResult:
    bdmv = root / "BDMV"
    layout = BdmvLayout(
        root,
        root,
        bdmv,
        bdmv / "index.bdmv",
        bdmv / "PLAYLIST",
        bdmv / "CLIPINF",
        bdmv / "STREAM",
    )
    playlist = PlaylistInfo(
        bdmv / "PLAYLIST" / "00001.mpls",
        "00001",
        MediaTick90k(90_000),
        (),
        (),
        timeline_fingerprint=(("00001", 0, 45_000, 0),),
    )
    return ScanResult(layout, (playlist,))


def test_project_scan_identity_accepts_exact_saved_sources(tmp_path: Path) -> None:
    result = verify_project_scan_identity(_state(tmp_path), _identity_scan(tmp_path))

    assert result.ready
    assert result.playlist is not None
    assert result.playlist.stem == "00001"


def test_project_scan_identity_rejects_different_index_path(tmp_path: Path) -> None:
    scan = _identity_scan(tmp_path)
    assert scan.layout is not None
    changed = replace(
        scan,
        layout=replace(scan.layout, index_bdmv_path=tmp_path / "other" / "index.bdmv"),
    )

    result = verify_project_scan_identity(_state(tmp_path), changed)

    assert result.error_code == "project.index_mismatch"


def test_project_scan_identity_rejects_path_or_timeline_mismatch(
    tmp_path: Path,
) -> None:
    scan = _identity_scan(tmp_path)
    wrong_path = replace(
        scan,
        playlists=(replace(scan.playlists[0], path=tmp_path / "00001.mpls"),),
    )
    wrong_timeline = replace(
        scan,
        playlists=(
            replace(
                scan.playlists[0],
                timeline_fingerprint=(("00002", 0, 45_000, 0),),
            ),
        ),
    )

    assert (
        verify_project_scan_identity(_state(tmp_path), wrong_path).error_code
        == "project.playlist_missing"
    )
    assert (
        verify_project_scan_identity(_state(tmp_path), wrong_timeline).error_code
        == "project.playlist_changed"
    )


@pytest.mark.parametrize("source_state", (SourceState.MISSING, SourceState.CHANGED))
def test_changed_or_missing_source_blocks_before_scan(
    tmp_path: Path,
    source_state: SourceState,
) -> None:
    fixture = _make_fixture(tmp_path)
    if source_state is SourceState.MISSING:
        fixture.subtitle_paths[0].unlink()
    else:
        fixture.subtitle_paths[0].write_text("changed source", encoding="utf-8")

    result, bdmv, subtitles, merge = _prepare(fixture)

    assert result.ready is False
    assert f"source_{source_state.value}" in _issue_codes(result)
    assert bdmv.requests == []
    assert subtitles.requests == []
    assert merge.requests == []


@pytest.mark.parametrize(
    ("mutate_scan", "expected_code"),
    (
        (
            lambda scan, root: replace(
                scan,
                layout=replace(
                    scan.layout,
                    index_bdmv_path=root / "different" / "index.bdmv",
                ),
            ),
            "project.index_mismatch",
        ),
        (
            lambda scan, root: replace(
                scan,
                playlists=(
                    replace(
                        scan.playlists[0],
                        path=root / "different" / "00001.mpls",
                    ),
                ),
            ),
            "project.playlist_missing",
        ),
        (
            lambda scan, _root: replace(
                scan,
                playlists=(
                    replace(scan.playlists[0], duration_90k=MediaTick90k(180_001)),
                ),
            ),
            "project.playlist_changed",
        ),
        (
            lambda scan, _root: replace(
                scan,
                playlists=(
                    replace(
                        scan.playlists[0],
                        timeline_fingerprint=(("changed", 0, 45_000, 0),),
                    ),
                ),
            ),
            "project.playlist_changed",
        ),
    ),
)
def test_scan_identity_mismatch_blocks_before_subtitle_load(
    tmp_path: Path,
    mutate_scan: Callable[[ScanResult, Path], ScanResult],
    expected_code: str,
) -> None:
    fixture = _make_fixture(tmp_path)
    assert fixture.scan.layout is not None

    result, bdmv, subtitles, merge = _prepare(
        fixture,
        scan=mutate_scan(fixture.scan, fixture.root),
    )

    assert result.ready is False
    assert expected_code in _issue_codes(result)
    assert len(bdmv.requests) == 1
    assert subtitles.requests == []
    assert merge.requests == []


@pytest.mark.parametrize(
    ("mutate_subtitles", "expected_code"),
    (
        (
            lambda result, root: replace(
                result,
                assets=(replace(result.assets[0], path=root / "other.ass"), *result.assets[1:]),
            ),
            "subtitle_path_mismatch",
        ),
        (
            lambda result, _root: replace(
                result,
                assets=(replace(result.assets[0], format=SubtitleFormat.SRT), *result.assets[1:]),
            ),
            "subtitle_format_mismatch",
        ),
        (
            lambda result, _root: replace(result, assets=result.assets[:1]),
            "subtitle_count_mismatch",
        ),
    ),
)
def test_subtitle_identity_mismatch_blocks_before_merge_prepare(
    tmp_path: Path,
    mutate_subtitles: Callable[[LoadSubtitlesResult, Path], LoadSubtitlesResult],
    expected_code: str,
) -> None:
    fixture = _make_fixture(tmp_path)

    result, _, subtitles, merge = _prepare(
        fixture,
        subtitles=mutate_subtitles(fixture.subtitles, fixture.root),
    )

    assert result.ready is False
    assert expected_code in _issue_codes(result)
    assert len(subtitles.requests) == 1
    assert merge.requests == []


def test_every_saved_mapping_is_an_exact_reproduction_constraint(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)

    result, _, _, merge = _prepare(fixture)

    assert result.ready is True
    assert len(merge.requests) == 1
    assert [
        (
            lock.episode_id,
            int(lock.manual_offset_90k),
        )
        for lock in merge.requests[0].locks
    ] == [
        ("episode-1", 900),
        ("episode-2", 0),
    ]
    assert [mapping.locked for mapping in result.restored.state.mappings] == [
        True,
        False,
    ]


def test_saved_non_candidate_boundaries_become_exact_solver_constraints(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    boundaries = (
        BoundarySnapshot("saved-10", 10),
        BoundarySnapshot("saved-40", 40),
        BoundarySnapshot("saved-50", 50),
        BoundarySnapshot("saved-90", 90),
    )
    mappings = (
        MappingSnapshot(
            "first",
            "saved-10",
            "saved-40",
            10,
            40,
            7,
            True,
            "high",
        ),
        MappingSnapshot(
            "second",
            "saved-50",
            "saved-90",
            50,
            90,
            -3,
            False,
            "high",
        ),
    )

    result, _, _, merge = _prepare(
        fixture,
        project=replace(fixture.project, boundaries=boundaries, mappings=mappings),
    )

    assert result.ready is True
    request = merge.requests[0]
    runtime_boundaries = {
        item.id: int(item.time_90k) for item in request.additional_boundaries
    }
    assert [
        (
            runtime_boundaries[lock.start_boundary_id],
            runtime_boundaries[lock.end_boundary_id],
            int(lock.manual_offset_90k),
        )
        for lock in request.locks
    ] == [(10, 40, 7), (50, 90, -3)]
    assert [mapping.locked for mapping in result.restored.state.mappings] == [
        True,
        False,
    ]


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    (
        (
            lambda mapping: replace(
                mapping,
                mappings=(
                    replace(mapping.mappings[0], manual_offset_90k=MediaTick90k(901)),
                    mapping.mappings[1],
                ),
            ),
            "manual offset",
        ),
        (
            lambda mapping: replace(
                mapping,
                mappings=(
                    replace(mapping.mappings[0], end_boundary=mapping.mappings[1].end_boundary),
                    mapping.mappings[1],
                ),
            ),
            "end boundary",
        ),
    ),
)
def test_mapping_reproduction_mismatch_is_reported(
    tmp_path: Path,
    mutation: Callable[[MappingResult], MappingResult],
    expected_fragment: str,
) -> None:
    fixture = _make_fixture(tmp_path)

    result, _, _, _ = _prepare(fixture, mapping_transform=mutation)

    issues = [issue for issue in result.issues if issue.code == "mapping_reproduction_failed"]
    assert result.ready is False
    assert len(issues) == 1
    assert expected_fragment in issues[0].message


def test_mapping_failure_preserves_underlying_and_reproduction_issues(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    mapping_failure = ApplicationIssue(
        ApplicationSeverity.ERROR,
        "mapping_failed",
        "saved mapping boundary is invalid",
    )

    result, _, _, _ = _prepare(
        fixture,
        merge_issues=(mapping_failure,),
        omit_mapping=True,
    )

    assert result.ready is False
    assert _issue_codes(result) >= {
        "mapping_failed",
        "mapping_reproduction_failed",
    }


def test_conflict_policy_and_output_target_are_projected_without_losing_state(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)

    result, _, _, merge = _prepare(fixture)

    assert result.ready is True
    request = merge.requests[0]
    assert request.merge_options is not None
    assert request.merge_options.playlist_end_ticks == 180_000
    assert request.merge_options.accept_script_info_conflicts is True
    assert request.merge_options.keep_events_ending_before_zero is True
    assert request.merge_options.clip_negative_starts is False
    assert result.project.conflict_policy.preserve_unknown_sections is False
    assert result.restored.state.conflict_policy.preserve_unknown_sections is False
    assert len(request.output_targets) == 1
    target = request.output_targets[0]
    assert isinstance(target, FullPathOutputTarget)
    assert target.path == fixture.output_path
    assert target.encoding == "utf-8-sig"
    assert target.collision_policy is CollisionPolicy.AUTO_RENAME
    assert result.project.outputs[0].preset == "jriver"
    assert result.project.outputs[0].path_template == "legacy-{playlist}"
    assert result.project.outputs[0].backup_policy == "backup"
    assert result.restored.state.outputs[0].preset == "jriver"
    assert result.restored.state.outputs[0].path_template == "legacy-{playlist}"
    assert result.restored.state.outputs[0].resolved_path == fixture.output_path
    assert result.restored.state.outputs[0].backup_policy == "backup"


def test_source_change_after_subtitle_load_blocks_final_commit(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)

    def change_source() -> None:
        fixture.subtitle_paths[1].write_text("changed after load", encoding="utf-8")

    result, bdmv, subtitles, merge = _prepare(fixture, after_load=change_source)

    assert result.ready is False
    assert "source_changed" in _issue_codes(result)
    assert len(bdmv.requests) == 1
    assert len(subtitles.requests) == 1
    assert len(merge.requests) == 1


def test_merge_detected_source_race_blocks_success(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    race = ApplicationIssue(
        ApplicationSeverity.ERROR,
        "source_changed_during_prepare",
        "subtitle changed during merge preparation",
        str(fixture.subtitle_paths[0]),
    )

    result, _, _, merge = _prepare(fixture, merge_issues=(race,))

    assert result.ready is False
    assert "source_changed_during_prepare" in _issue_codes(result)
    assert len(merge.requests) == 1


def test_success_returns_complete_runtime_state_and_refreshes_subtitle_metadata(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)

    result, bdmv, subtitles, merge = _prepare(fixture)

    assert result.ready is True
    assert result.scan is fixture.scan
    assert result.playlist is fixture.scan.playlists[0]
    assert result.subtitles is fixture.subtitles
    assert result.prepared is not None
    assert result.prepared.mapping is not None
    assert bdmv.requests == [ScanRequest(fixture.bdmv)]
    assert tuple(source.path for source in subtitles.requests[0].sources) == (
        fixture.subtitle_paths
    )
    assert len(merge.requests) == 1
    assert result.restored.state.bdmv_path == fixture.bdmv
    assert result.restored.state.playlist_path == fixture.playlist_path
    assert result.restored.state.ui_notes == "saved note"
    assert result.restored.has_changed_sources is False
    assert [subtitle.event_count for subtitle in result.project.subtitles] == [3, 3]
    assert [subtitle.style_count for subtitle in result.project.subtitles] == [2, 2]
    assert [subtitle.raw_end_90k for subtitle in result.project.subtitles] == [
        100_000,
        120_000,
    ]
    assert [subtitle.effective_end_90k for subtitle in result.project.subtitles] == [
        90_000,
        90_000,
    ]
    assert result.project.subtitles[1].warnings == ("duration estimated",)
    assert [mapping.manual_offset_90k for mapping in result.restored.state.mappings] == [
        900,
        0,
    ]
