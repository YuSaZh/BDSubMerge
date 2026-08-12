from pathlib import Path

import pytest

from bdsubmerge.output import (
    AtomicWriteError,
    CollisionPolicy,
    FullPathOutputTarget,
    OutputContext,
    ResolvedOutput,
    preflight_outputs,
    write_outputs_atomically,
)


def test_atomic_writer_commits_all_staged_outputs(tmp_path: Path) -> None:
    targets = (
        FullPathOutputTarget("first", path=tmp_path / "first.ass"),
        FullPathOutputTarget("second", path=tmp_path / "second.ass"),
    )
    preflight = preflight_outputs(targets, OutputContext(subtitle_format="ass"))

    receipt = write_outputs_atomically(preflight, {"first": "one", "second": b"two"})

    assert receipt.paths == (tmp_path / "first.ass", tmp_path / "second.ass")
    assert (tmp_path / "first.ass").read_text(encoding="utf-8-sig") == "one"
    assert (tmp_path / "second.ass").read_bytes() == b"two"
    assert not tuple(tmp_path.glob("*.tmp"))


def test_backup_policy_preserves_previous_destination(tmp_path: Path) -> None:
    destination = tmp_path / "index.ass"
    destination.write_bytes(b"old")
    target = FullPathOutputTarget("target", CollisionPolicy.BACKUP, path=destination)
    preflight = preflight_outputs((target,), OutputContext(subtitle_format="ass"))

    receipt = write_outputs_atomically(preflight, {"target": b"new"})

    assert destination.read_bytes() == b"new"
    assert receipt.backups == (tmp_path / "index.ass.bak",)
    assert receipt.backups[0].read_bytes() == b"old"


def test_validation_failure_leaves_no_outputs_or_temporary_files(tmp_path: Path) -> None:
    targets = (
        FullPathOutputTarget("first", path=tmp_path / "first.srt"),
        FullPathOutputTarget("second", path=tmp_path / "second.srt"),
    )
    preflight = preflight_outputs(targets, OutputContext(subtitle_format="srt"))

    def reject_second(path: Path, output: ResolvedOutput) -> None:
        del path
        if output.target_id == "second":
            raise AtomicWriteError("invalid staged subtitle")

    with pytest.raises(AtomicWriteError, match="invalid staged subtitle"):
        write_outputs_atomically(
            preflight,
            {"first": b"one", "second": b"two"},
            validator=reject_second,
        )

    assert list(tmp_path.iterdir()) == []


def test_failed_multi_target_commit_restores_overwritten_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.ass"
    first.write_bytes(b"old")
    targets = (
        FullPathOutputTarget("first", CollisionPolicy.OVERWRITE, path=first),
        FullPathOutputTarget("second", path=tmp_path / "second.ass"),
    )
    preflight = preflight_outputs(targets, OutputContext(subtitle_format="ass"))
    real_replace = Path.replace
    commits = 0

    def fail_second_commit(source: Path, destination: Path) -> Path:
        nonlocal commits
        if str(source).endswith(".tmp"):
            commits += 1
            if commits == 2:
                raise OSError("simulated commit failure")
        return real_replace(source, destination)

    monkeypatch.setattr(Path, "replace", fail_second_commit)

    with pytest.raises(AtomicWriteError, match="simulated commit failure"):
        write_outputs_atomically(preflight, {"first": b"new", "second": b"new"})

    assert first.read_bytes() == b"old"
    assert not (tmp_path / "second.ass").exists()
    assert not tuple(tmp_path.glob(".*.tmp"))
    assert not tuple(tmp_path.glob(".*.rollback"))
