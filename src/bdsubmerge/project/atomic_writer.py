"""Crash-resistant atomic writes for project JSON files."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from .persistence import dump_project_bytes
from .schema import ProjectSnapshot


class WritableBinary(Protocol):
    def write(self, data: bytes) -> int: ...

    def flush(self) -> None: ...

    def fileno(self) -> int: ...

    def close(self) -> None: ...


type BinaryOpener = Callable[[int, str], WritableBinary]
type Replacer = Callable[[Path, Path], None]


class AtomicProjectWriteError(OSError):
    """A project could not be committed atomically."""


def _open_descriptor(descriptor: int, mode: str) -> WritableBinary:
    return cast(WritableBinary, os.fdopen(descriptor, mode))


def _write_all(stream: WritableBinary, data: bytes) -> None:
    position = 0
    while position < len(data):
        written = stream.write(data[position:])
        if written <= 0:
            raise OSError("project writer made no forward progress")
        position += written


def atomic_project_writer(
    path: Path,
    data: bytes,
    *,
    opener: BinaryOpener = _open_descriptor,
    replacer: Replacer = os.replace,
) -> None:
    """Write bytes beside the destination and atomically replace it."""

    destination = path.absolute()
    directory = destination.parent
    descriptor = -1
    temporary_path: Path | None = None
    stream: WritableBinary | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=directory,
        )
        temporary_path = Path(temporary_name)
        stream = opener(descriptor, "wb")
        descriptor = -1
        _write_all(stream, data)
        stream.flush()
        os.fsync(stream.fileno())
        stream.close()
        stream = None
        replacer(temporary_path, destination)
    except (OSError, ValueError) as error:
        raise AtomicProjectWriteError(f"could not atomically save project {destination}") from error
    finally:
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
        elif descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def atomic_save_project(project: ProjectSnapshot, path: Path) -> None:
    """Serialize a project and atomically commit the resulting UTF-8 JSON."""

    atomic_project_writer(path, dump_project_bytes(project))
