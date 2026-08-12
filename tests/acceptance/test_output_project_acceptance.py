import os
import sys
from pathlib import Path, PureWindowsPath
from typing import cast

import pytest

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
    bdmv = Path(unc_root) / "中文原盘" / "BDMV"
    bdmv.mkdir(parents=True)
    index = bdmv / "index.bdmv"
    index.write_bytes(b"immutable index")
    preflight = preflight_outputs(
        (JRiverOutputTarget("jriver"),),
        OutputContext(subtitle_format="ass", index_bdmv_path=index),
    )

    receipt = write_outputs_atomically(preflight, {"jriver": "UNC subtitle"})

    expected = bdmv / "index.ass"
    assert receipt.paths == (expected,)
    assert expected.read_text(encoding="utf-8-sig") == "UNC subtitle"
    assert tuple(bdmv.glob(".*.tmp")) == ()
    assert tuple(bdmv.glob(".*.rollback")) == ()


def test_ac06_project_save_load_restore_is_deterministic_for_unchanged_inputs(
    tmp_path: Path,
) -> None:
    project_file = tmp_path / "projects" / "show.bdsm.json"
    bdmv = tmp_path / "media" / "Title" / "BDMV"
    index = bdmv / "index.bdmv"
    playlist = bdmv / "PLAYLIST" / "00001.mpls"
    subtitle = tmp_path / "subtitles" / "E01.ass"
    playlist.parent.mkdir(parents=True)
    subtitle.parent.mkdir(parents=True)
    index.write_bytes(b"immutable index")
    playlist.write_bytes(b"immutable playlist")
    subtitle.write_bytes(b"immutable subtitle")
    boundaries = (
        BoundarySnapshot("start", 0, ("playlist_start",), ("playlist",)),
        BoundarySnapshot("end", 180_000, ("chapter",), ("mark:0",)),
    )
    mappings = (
        MappingSnapshot("E01", "start", "end", 0, 180_000, 900, True, "high"),
    )
    outputs = (
        OutputState(
            "jriver",
            "jriver",
            "",
            bdmv / "index.ass",
            "utf-8-sig",
            "abort",
        ),
    )
    state = ProjectState(
        bdmv,
        index,
        playlist,
        "00001",
        180_000,
        (("00001", 0, 90_000, 0),),
        (
            SubtitleState(
                "E01",
                subtitle,
                "ass",
                "utf-8-sig",
                0,
                179_000,
                178_000,
                12,
                2,
                (("language", "zh-CN"),),
            ),
        ),
        boundaries,
        mappings,
        outputs,
        ConflictPolicySnapshot(accept_script_info_conflicts=True),
        "accepted mapping",
    )
    snapshot = build_project_snapshot(state, project_file=project_file)

    project_file.parent.mkdir()
    atomic_save_project(snapshot, project_file)
    loaded = load_project_bytes(project_file.read_bytes())
    restored = restore_project_state(loaded, project_file=project_file)

    assert loaded == snapshot
    assert restored.state == state
    assert restored.state.mappings == mappings
    assert restored.state.outputs == outputs
    assert restored.state.conflict_policy == state.conflict_policy
    assert restored.state.ui_notes == "accepted mapping"
    assert restored.has_changed_sources is False
    assert all(check.state is SourceState.UNCHANGED for check in restored.source_checks)


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
