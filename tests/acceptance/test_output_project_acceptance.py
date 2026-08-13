import os
import sys
from pathlib import Path, PureWindowsPath
from typing import cast

import pytest

from bdsubmerge.application import (
    ApplicationSeverity,
    BdmvApplicationService,
    ExecuteMergeRequest,
    LoadSubtitlesRequest,
    MergeApplicationService,
    PrepareMergeRequest,
    ScanRequest,
    SubtitleApplicationService,
    SubtitleInput,
    build_playlist_boundaries,
)
from bdsubmerge.mapping import MappingLock, TimelineBoundary
from bdsubmerge.merge import MergeOptions
from bdsubmerge.output import (
    CollisionPolicy,
    FullPathOutputTarget,
    JRiverOutputTarget,
    OutputContext,
    OutputPreflightError,
    preflight_outputs,
    write_outputs_atomically,
)
from bdsubmerge.project import (
    BoundarySnapshot,
    ConflictPolicySnapshot,
    MappingSnapshot,
    OutputState,
    ProjectState,
    SourceState,
    SubtitleState,
    atomic_save_project,
    build_project_snapshot,
    load_project_bytes,
    restore_project_state,
)

SHINYA_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "shinya" / "minimal_playlist.mpls.hex"
)
ASS_EPISODE = (
    b"[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
    b"[V4+ Styles]\nFormat: Name\nStyle: Default\n"
    b"[Events]\nFormat: Start, End, Style, Text\n"
    b"Dialogue: 0:00:00.00,0:00:00.90,Default,line\n"
)


def _shinya_fixture_bytes() -> bytes:
    lines = (
        line.strip()
        for line in SHINYA_FIXTURE.read_text(encoding="ascii").splitlines()
        if line and not line.startswith("#")
    )
    return bytes.fromhex("".join(lines))


def _write_minimal_bdmv(disc: Path) -> tuple[Path, ...]:
    bdmv = disc / "BDMV"
    playlist = bdmv / "PLAYLIST" / "00001.mpls"
    clip_info = bdmv / "CLIPINF" / "00001.clpi"
    stream = bdmv / "STREAM" / "00001.m2ts"
    for directory in (playlist.parent, clip_info.parent, stream.parent):
        directory.mkdir(parents=True, exist_ok=True)
    index = bdmv / "index.bdmv"
    index.write_bytes(b"immutable index")
    playlist.write_bytes(_shinya_fixture_bytes())
    clip_info.write_bytes(b"immutable clip metadata")
    stream.write_bytes(b"immutable media")
    return index, playlist, clip_info, stream


def _source_metadata(paths: tuple[Path, ...]) -> tuple[tuple[Path, int, int], ...]:
    return tuple((path, path.stat().st_size, path.stat().st_mtime_ns) for path in paths)


def _boundary_snapshot(boundary_item: TimelineBoundary) -> BoundarySnapshot:
    return BoundarySnapshot(
        boundary_item.id,
        int(boundary_item.time_90k),
        tuple(sorted(source.kind.value for source in boundary_item.sources)),
        tuple(source.reference for source in boundary_item.sources),
        boundary_item.confidence,
        boundary_item.enabled,
        boundary_item.user_created,
        boundary_item.note,
    )


def test_ac01_jriver_resolves_only_exact_index_ass_path(tmp_path: Path) -> None:
    bdmv = tmp_path / "Title" / "BDMV"
    bdmv.mkdir(parents=True)
    index = bdmv / "index.bdmv"
    index.write_bytes(b"immutable index")
    context = OutputContext(subtitle_format="ass", index_bdmv_path=index)
    target = JRiverOutputTarget("jriver")

    preflight = preflight_outputs((target,), context)
    receipt = write_outputs_atomically(preflight, {"jriver": "merged subtitle"})

    assert preflight.ready is True
    assert len(preflight.outputs) == 1
    assert preflight.outputs[0].path == bdmv / "index.ass"
    assert preflight.outputs[0].path.name == "index.ass"
    assert receipt.paths == (bdmv / "index.ass",)
    assert (bdmv / "index.ass").read_text(encoding="utf-8-sig") == "merged subtitle"
    assert tuple(path.name for path in bdmv.glob("*.ass")) == ("index.ass",)
    assert not (bdmv / "index.bdmv.ass").exists()


def test_ac02_unc_jriver_path_logic_is_portable() -> None:
    index = PureWindowsPath(r"\\hpserver\storage\Anime\Title\BDMV\index.bdmv")
    target = JRiverOutputTarget("jriver")

    resolved = target.resolve_path(OutputContext("ass", index_bdmv_path=cast(Path, index)))

    assert resolved == PureWindowsPath(
        r"\\hpserver\storage\Anime\Title\BDMV\index.ass"
    )
    assert resolved.is_absolute() is True


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows UNC Path semantics")
def test_ac02_windows_unc_target_reaches_preflight_without_path_corruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = Path(r"\\nonexistent-bdsubmerge-share\Anime\Title\BDMV\index.bdmv")
    context = OutputContext(subtitle_format="ass", index_bdmv_path=index)
    monkeypatch.setattr(Path, "exists", lambda self: False)

    preflight = preflight_outputs(
        (JRiverOutputTarget("jriver"),),
        context,
        require_existing_sources=False,
    )

    assert preflight.outputs[0].path == index.with_suffix(".ass")
    assert preflight.outputs[0].path.is_absolute() is True
    assert "resolve_failed" not in {issue.code for issue in preflight.issues}
    assert "format_mismatch" not in {issue.code for issue in preflight.issues}
    assert "missing_output_directory" in {issue.code for issue in preflight.issues}


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows SMB support")
def test_ac02_windows_unc_target_is_written_atomically() -> None:
    unc_root = os.environ.get("BDSUBMERGE_TEST_UNC_ROOT")
    assert unc_root, "Windows CI must provide its isolated temporary UNC share"
    disc = Path(unc_root) / "中文原盘"
    sources = _write_minimal_bdmv(disc)
    before = _source_metadata(sources)

    scan = BdmvApplicationService().scan(ScanRequest(disc))

    assert scan.ready is True
    assert scan.layout is not None
    assert scan.layout.index_bdmv_path == sources[0].resolve(strict=False)
    assert len(scan.playlists) == 1
    playlist = scan.playlists[0]
    assert playlist.path == sources[1].resolve(strict=False)
    assert playlist.is_available is True
    assert playlist.duration_90k == 90_000
    preflight = preflight_outputs(
        (JRiverOutputTarget("jriver"),),
        OutputContext(
            subtitle_format="ass",
            index_bdmv_path=scan.layout.index_bdmv_path,
            playlist_path=playlist.path,
            disc_container_path=scan.layout.disc_container_path,
        ),
    )

    receipt = write_outputs_atomically(preflight, {"jriver": "UNC subtitle"})

    expected = scan.layout.bdmv_path / "index.ass"
    assert preflight.ready is True
    assert receipt.paths == (expected,)
    assert expected.read_text(encoding="utf-8-sig") == "UNC subtitle"
    assert tuple(scan.layout.bdmv_path.glob(".*.tmp")) == ()
    assert tuple(scan.layout.bdmv_path.glob(".*.rollback")) == ()
    assert _source_metadata(sources) == before


def test_ac06_project_save_load_restore_is_deterministic_for_unchanged_inputs(
    tmp_path: Path,
) -> None:
    project_file = tmp_path / "projects" / "show.bdsm.json"
    disc = tmp_path / "media" / "Title"
    sources = _write_minimal_bdmv(disc)
    before = _source_metadata(sources)
    subtitle = tmp_path / "subtitles" / "E01.ass"
    subtitle.parent.mkdir(parents=True)
    subtitle.write_bytes(ASS_EPISODE)
    output = tmp_path / "outputs" / "merged.ass"
    output.parent.mkdir()
    output_target = FullPathOutputTarget(
        "main",
        collision_policy=CollisionPolicy.AUTO_RENAME,
        path=output,
    )
    conflict_policy = ConflictPolicySnapshot(accept_script_info_conflicts=True)
    merge_options = MergeOptions(
        playlist_end_ticks=90_000,
        accept_script_info_conflicts=conflict_policy.accept_script_info_conflicts,
        keep_events_ending_before_zero=conflict_policy.keep_events_ending_before_zero,
        clip_negative_starts=conflict_policy.clip_negative_starts,
    )
    scan = BdmvApplicationService().scan(ScanRequest(disc))
    loaded_subtitles = SubtitleApplicationService().load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle),))
    )
    assert scan.ready is True
    assert scan.layout is not None
    assert len(scan.playlists) == 1
    playlist = scan.playlists[0]
    assert playlist.is_available is True
    assert loaded_subtitles.ready is True
    automatic = MergeApplicationService().prepare(
        PrepareMergeRequest(
            scan.layout,
            playlist,
            loaded_subtitles,
            (output_target,),
            accept_low_confidence=True,
        )
    )
    assert automatic.mapping is not None
    locks = tuple(
        MappingLock(
            item.episode_id,
            item.start_boundary.id,
            item.end_boundary.id,
            item.manual_offset_90k,
        )
        for item in automatic.mapping.mappings
    )
    authored = MergeApplicationService().prepare(
        PrepareMergeRequest(
            scan.layout,
            playlist,
            loaded_subtitles,
            (output_target,),
            locks=locks,
            merge_options=merge_options,
            accept_low_confidence=True,
        )
    )
    assert authored.ready is True
    assert authored.mapping is not None
    assert authored.report is not None
    assert all(item.locked for item in authored.mapping.mappings)
    runtime_boundaries = build_playlist_boundaries(playlist)
    boundaries = tuple(_boundary_snapshot(item) for item in runtime_boundaries)
    mappings = tuple(
        MappingSnapshot(
            "E01",
            item.start_boundary.id,
            item.end_boundary.id,
            int(item.start_boundary.time_90k),
            int(item.end_boundary.time_90k),
            int(item.manual_offset_90k),
            True,
            item.confidence.value,
            item.warnings,
        )
        for item in authored.mapping.mappings
    )
    asset = loaded_subtitles.assets[0]
    outputs = (
        OutputState(
            output_target.target_id,
            output_target.preset.value,
            "",
            output,
            output_target.encoding,
            output_target.collision_policy.value,
        ),
    )
    state = ProjectState(
        scan.layout.bdmv_path,
        scan.layout.index_bdmv_path,
        playlist.path,
        playlist.stem,
        int(playlist.duration_90k),
        playlist.timeline_fingerprint,
        (
            SubtitleState(
                "E01",
                subtitle,
                asset.format.value,
                asset.encoding or "utf-8",
                0,
                asset.analysis.raw_end_ticks,
                asset.analysis.effective_end_ticks,
                asset.analysis.event_count,
                asset.analysis.style_count,
            ),
        ),
        boundaries,
        mappings,
        outputs,
        conflict_policy,
        "accepted mapping",
    )
    snapshot = build_project_snapshot(state, project_file=project_file)

    project_file.parent.mkdir()
    atomic_save_project(snapshot, project_file)
    reproduced = []
    restored_states = []
    for _ in range(2):
        loaded = load_project_bytes(project_file.read_bytes())
        restored = restore_project_state(loaded, project_file=project_file)
        restored_states.append(restored.state)
        assert loaded == snapshot
        assert restored.has_changed_sources is False
        assert all(check.state is SourceState.UNCHANGED for check in restored.source_checks)

        reopened_scan = BdmvApplicationService().scan(ScanRequest(restored.state.bdmv_path))
        assert reopened_scan.ready is True
        assert reopened_scan.layout is not None
        reopened_playlist = next(
            item
            for item in reopened_scan.playlists
            if item.stem == restored.state.playlist_stem
        )
        ordered = tuple(sorted(restored.state.subtitles, key=lambda item: item.order))
        reopened_subtitles = SubtitleApplicationService().load_ordered(
            LoadSubtitlesRequest(
                tuple(SubtitleInput(item.path, item.encoding) for item in ordered)
            )
        )
        restored_outputs = tuple(
            FullPathOutputTarget(
                item.id,
                collision_policy=CollisionPolicy(item.collision_policy),
                encoding=item.encoding,
                path=cast(Path, item.resolved_path),
            )
            for item in restored.state.outputs
        )
        restored_locks = tuple(
            MappingLock(
                f"episode-{index + 1}",
                item.start_boundary_id,
                item.end_boundary_id,
                item.manual_offset_90k,
            )
            for index, item in enumerate(restored.state.mappings)
        )
        policy = restored.state.conflict_policy
        prepared = MergeApplicationService().prepare(
            PrepareMergeRequest(
                reopened_scan.layout,
                reopened_playlist,
                reopened_subtitles,
                restored_outputs,
                locks=restored_locks,
                merge_options=MergeOptions(
                    playlist_end_ticks=restored.state.playlist_duration_90k,
                    accept_script_info_conflicts=policy.accept_script_info_conflicts,
                    keep_events_ending_before_zero=policy.keep_events_ending_before_zero,
                    clip_negative_starts=policy.clip_negative_starts,
                ),
                accept_low_confidence=True,
            )
        )
        if reproduced:
            renamed = tuple(
                issue
                for issue in prepared.issues
                if issue.code == "output_destination_renamed"
            )
            assert len(renamed) == 1
            assert renamed[0].severity is ApplicationSeverity.INFO
        executed = MergeApplicationService().execute(ExecuteMergeRequest(prepared))

        assert prepared.mapping == authored.mapping
        assert prepared.report == authored.report
        assert executed.succeeded is True
        assert executed.receipt is not None
        reproduced.append(
            (prepared.mapping, prepared.report, executed.receipt.paths[0].read_bytes())
        )

    assert restored_states[0] == restored_states[1] == state
    assert all(item.mappings == mappings for item in restored_states)
    assert all(item.outputs == outputs for item in restored_states)
    assert all(item.conflict_policy == conflict_policy for item in restored_states)
    assert all(item.ui_notes == "accepted mapping" for item in restored_states)
    assert reproduced[0] == reproduced[1]
    assert output.is_file()
    assert output.with_name("merged (1).ass").is_file()
    assert tuple(output.parent.glob(".*.tmp")) == ()
    assert tuple(output.parent.glob(".*.rollback")) == ()
    assert _source_metadata(sources) == before


def test_ac07_abort_preflight_writes_no_multi_target_outputs_or_temps(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "existing.ass"
    untouched = tmp_path / "untouched.ass"
    existing.write_bytes(b"original")
    targets = (
        FullPathOutputTarget(
            "existing",
            collision_policy=CollisionPolicy.ABORT,
            path=existing,
        ),
        FullPathOutputTarget(
            "untouched",
            collision_policy=CollisionPolicy.ABORT,
            path=untouched,
        ),
    )
    preflight = preflight_outputs(targets, OutputContext(subtitle_format="ass"))

    assert preflight.ready is False
    assert "destination_exists" in {issue.code for issue in preflight.errors}
    with pytest.raises(OutputPreflightError):
        write_outputs_atomically(
            preflight,
            {"existing": b"replacement", "untouched": b"new output"},
        )

    assert existing.read_bytes() == b"original"
    assert not untouched.exists()
    assert tuple(tmp_path.glob(".*.tmp")) == ()
    assert tuple(tmp_path.glob(".*.rollback")) == ()
