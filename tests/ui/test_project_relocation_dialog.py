"""Tests for the modal project source relocation dialog."""

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox
from pytestqt.qtbot import QtBot

from bdsubmerge.project import (
    FileFingerprint,
    ProjectState,
    RestoredProject,
    SourceCheck,
    SourceState,
)
from bdsubmerge.ui.project_relocation import ProjectRelocationDialog


def _restored(tmp_path: Path) -> RestoredProject:
    state = ProjectState(
        tmp_path / "BDMV",
        tmp_path / "BDMV" / "index.bdmv",
        tmp_path / "BDMV" / "PLAYLIST" / "00001.mpls",
        "00001",
        90_000,
        (),
        (),
        (),
        (),
        (),
    )
    fingerprint = FileFingerprint(1, 1)
    return RestoredProject(
        state,
        (
            SourceCheck(
                "index_bdmv",
                state.index_bdmv_path,
                SourceState.MISSING,
                fingerprint,
                None,
            ),
            SourceCheck(
                "episode-1",
                tmp_path / "episode.ass",
                SourceState.CHANGED,
                fingerprint,
                FileFingerprint(2, 2),
            ),
        ),
    )


def test_dialog_requires_every_source_to_be_resolved_before_continue(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    restored = _restored(tmp_path)
    relocated: list[str] = []

    def relocate(check: SourceCheck) -> RestoredProject:
        relocated.append(check.id)
        checks = tuple(
            replace(item, state=SourceState.UNCHANGED, actual=item.expected)
            if item.id == check.id
            else item
            for item in dialog.restored.source_checks
        )
        return replace(dialog.restored, source_checks=checks)

    dialog = ProjectRelocationDialog(
        restored,
        tr=lambda key, **_values: key,
        relocate=relocate,
    )
    qtbot.addWidget(dialog)

    assert dialog.sources.rowCount() == 2
    assert dialog.continue_button.isEnabled() is False
    assert dialog.locate_button.isEnabled() is True

    qtbot.mouseClick(dialog.locate_button, Qt.MouseButton.LeftButton)

    assert relocated == ["index_bdmv"]
    assert dialog.sources.rowCount() == 1
    assert dialog.continue_button.isEnabled() is False

    qtbot.mouseClick(dialog.locate_button, Qt.MouseButton.LeftButton)

    assert relocated == ["index_bdmv", "episode-1"]
    assert dialog.sources.rowCount() == 0
    assert dialog.locate_button.isEnabled() is False
    assert dialog.continue_button.isEnabled() is True


def test_dialog_cancel_button_rejects_recovery(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    dialog = ProjectRelocationDialog(
        _restored(tmp_path),
        tr=lambda key, **_values: key,
        relocate=lambda _check: None,
    )
    qtbot.addWidget(dialog)
    cancel = dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel is not None

    qtbot.mouseClick(cancel, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected.value
