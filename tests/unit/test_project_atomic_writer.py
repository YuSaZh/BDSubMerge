import os
from pathlib import Path

import pytest

from bdsubmerge.project.atomic_writer import (
    AtomicProjectWriteError,
    atomic_project_writer,
    atomic_save_project,
)
from bdsubmerge.project.persistence import load_project_bytes
from test_project_persistence import sample_project


def _temporary_files(directory: Path, destination_name: str) -> tuple[Path, ...]:
    return tuple(directory.glob(f".{destination_name}.*.tmp"))


def test_atomic_writer_replaces_destination_without_temporary_residue(tmp_path: Path) -> None:
    destination = tmp_path / "show.bdsm.json"
    destination.write_bytes(b"old project")

    atomic_project_writer(destination, b"new project")

    assert destination.read_bytes() == b"new project"
    assert _temporary_files(tmp_path, destination.name) == ()


def test_atomic_writer_handles_short_writes(tmp_path: Path) -> None:
    destination = tmp_path / "show.bdsm.json"

    class ShortWriter:
        def __init__(self, descriptor: int) -> None:
            self.stream = os.fdopen(descriptor, "wb")

        def write(self, data: bytes) -> int:
            return self.stream.write(data[:2])

        def flush(self) -> None:
            self.stream.flush()

        def fileno(self) -> int:
            return self.stream.fileno()

        def close(self) -> None:
            self.stream.close()

    def short_opener(descriptor: int, mode: str) -> ShortWriter:
        del mode
        return ShortWriter(descriptor)

    atomic_project_writer(destination, b"complete", opener=short_opener)

    assert destination.read_bytes() == b"complete"


def test_atomic_save_project_writes_loadable_json(tmp_path: Path) -> None:
    destination = tmp_path / "show.bdsm.json"

    atomic_save_project(sample_project(), destination)

    assert load_project_bytes(destination.read_bytes()) == sample_project()


def test_replace_failure_keeps_old_destination_and_cleans_temporary_file(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "show.bdsm.json"
    destination.write_bytes(b"old project")

    def fail_replace(source: Path, target: Path) -> None:
        del source, target
        raise OSError("replace failed")

    with pytest.raises(AtomicProjectWriteError, match="could not atomically save"):
        atomic_project_writer(destination, b"new project", replacer=fail_replace)

    assert destination.read_bytes() == b"old project"
    assert _temporary_files(tmp_path, destination.name) == ()


def test_write_failure_keeps_old_destination_and_cleans_temporary_file(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "show.bdsm.json"
    destination.write_bytes(b"old project")

    class FailingStream:
        def write(self, data: bytes) -> int:
            del data
            raise OSError("write failed")

        def flush(self) -> None:
            pass

        def fileno(self) -> int:
            return -1

        def close(self) -> None:
            pass

    def fail_opener(descriptor: int, mode: str) -> FailingStream:
        del mode
        os.close(descriptor)
        return FailingStream()

    with pytest.raises(AtomicProjectWriteError, match="could not atomically save"):
        atomic_project_writer(destination, b"new project", opener=fail_opener)

    assert destination.read_bytes() == b"old project"
    assert _temporary_files(tmp_path, destination.name) == ()
