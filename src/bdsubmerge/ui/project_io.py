"""Qt atomic persistence adapter for neutral project DTOs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QIODevice, QSaveFile

from bdsubmerge.project import (
    ProjectSnapshot,
    ProjectState,
    RestoredProject,
    build_project_snapshot,
    load_project_bytes,
    restore_project_state,
    save_project,
)


class ProjectWriteError(OSError):
    """QSaveFile could not atomically commit a project."""


def qt_atomic_project_writer(path: Path, data: bytes) -> None:
    destination = QSaveFile(str(path))
    if not destination.open(QIODevice.OpenModeFlag.WriteOnly):
        raise ProjectWriteError(destination.errorString())
    written = destination.write(data)
    if written != len(data):
        destination.cancelWriting()
        raise ProjectWriteError(destination.errorString() or "incomplete project write")
    if not destination.commit():
        raise ProjectWriteError(destination.errorString() or "project commit failed")


def save_project_atomically(project: ProjectSnapshot, path: Path) -> None:
    save_project(project, path, writer=qt_atomic_project_writer)


def load_restored_project(path: Path) -> tuple[ProjectSnapshot, RestoredProject]:
    project = load_project_bytes(path.read_bytes())
    return project, restore_project_state(project, project_file=path)


def capture_and_save(state: ProjectState, path: Path) -> ProjectSnapshot:
    snapshot = build_project_snapshot(state, project_file=path)
    save_project_atomically(snapshot, path)
    return snapshot
