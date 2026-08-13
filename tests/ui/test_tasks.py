from pathlib import Path
from threading import Event
from typing import cast

import pytest
from PySide6.QtCore import QSettings, Qt, QThreadPool
from pytestqt.qtbot import QtBot

from bdsubmerge.cancellation import raise_if_cancelled, report_progress
from bdsubmerge.project import RestoredProject
from bdsubmerge.ui.main_window import MainWindow
from bdsubmerge.ui.tasks import CancellationToken, ServiceTask


def _settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_service_task_delivers_result(qtbot: QtBot) -> None:
    task: ServiceTask[str] = ServiceTask(lambda: "done")

    with qtbot.waitSignal(task.signals.succeeded, timeout=3000) as signal:
        QThreadPool.globalInstance().start(task)

    assert signal.args == ["done"]


def test_service_task_forwards_operation_progress(qtbot: QtBot) -> None:
    progress: list[tuple[int, str]] = []

    def operation() -> str:
        report_progress(42, "episode.ass")
        return "done"

    task: ServiceTask[str] = ServiceTask(operation)
    task.signals.progress.connect(
        lambda value, detail: progress.append((value, detail))
    )

    with qtbot.waitSignal(task.signals.finished, timeout=3000):
        QThreadPool.globalInstance().start(task)

    assert (42, "episode.ass") in progress


def test_window_displays_current_task_file(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    current_path = str(tmp_path / "Subtitles" / "episode.ass")

    window._task_progress(42, current_path)

    assert window.progress.value() == 42
    assert window.task_detail.text() == "episode.ass"
    assert window.task_detail.toolTip() == current_path

    window._task_progress(100, "complete")

    assert window.task_detail.text() == ""
    assert window.task_detail.toolTip() == ""


def test_cancelled_task_does_not_run_operation(qtbot: QtBot) -> None:
    called = False

    def operation() -> str:
        nonlocal called
        called = True
        return "unexpected"

    token = CancellationToken()
    token.cancel()
    task: ServiceTask[str] = ServiceTask(operation, token=token)

    with qtbot.waitSignal(task.signals.cancelled, timeout=3000):
        QThreadPool.globalInstance().start(task)

    assert called is False


def test_running_service_task_exposes_token_to_operation_checkpoints(qtbot: QtBot) -> None:
    started = Event()
    resume = Event()
    token = CancellationToken()

    def operation() -> str:
        started.set()
        resume.wait(timeout=3)
        raise_if_cancelled()
        return "unexpected"

    task: ServiceTask[str] = ServiceTask(operation, token=token)
    QThreadPool.globalInstance().start(task)
    qtbot.waitUntil(started.is_set, timeout=3000)

    with qtbot.waitSignal(task.signals.cancelled, timeout=3000):
        token.cancel()
        resume.set()


def test_ac09_window_remains_responsive_and_cancel_suppresses_success(
    qtbot: QtBot, tmp_path: Path
) -> None:
    started = Event()
    release = Event()
    successes: list[object] = []
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window.show()

    def blocking_operation() -> str:
        started.set()
        release.wait(timeout=3)
        return "must be suppressed"

    window.pending_project = cast(RestoredProject, object())
    window._start_task(
        blocking_operation,
        "blocked",
        successes.append,
        kind="project_restore",
    )
    qtbot.waitUntil(started.is_set, timeout=3000)

    qtbot.mouseClick(window.advanced_toggle, Qt.MouseButton.LeftButton)
    assert window.advanced_toggle.isChecked() is False
    assert window.advanced_toggle.isEnabled() is False
    assert window.playlist_search.isEnabled() is False
    assert window.timeline_format.isEnabled() is False
    assert window.offset_spin.isEnabled() is False
    assert window.project_notes.isEnabled() is False
    assert window.active_task is not None

    window.cancel_active_task()
    release.set()
    qtbot.waitUntil(lambda: window.active_task is None, timeout=3000)

    assert successes == []
    assert window.cancellation is None
    assert window.pending_project is None
    assert window.task_status.text() == window.translations.text("task.cancelled")


def test_failed_project_task_keeps_failure_status_and_clears_restore_state(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window.pending_project = cast(RestoredProject, object())
    window.active_task_kind = "project_restore"

    window._task_failed("boom", "trace")
    window._task_finished()

    assert window.pending_project is None
    assert window.task_status.text() == window.translations.text("task.failed")
    assert "boom" in window.error_panel.toPlainText()


def test_subtitle_directory_import_is_cancelled_without_mutating_workspace(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = Event()
    release = Event()
    existing = tmp_path / "existing.ass"
    directory = tmp_path / "Subtitles"
    directory.mkdir()
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window.subtitle_paths = [existing]

    def blocking_import(request: object) -> object:
        del request
        started.set()
        release.wait(timeout=3)
        raise_if_cancelled()
        return object()

    monkeypatch.setattr(window.subtitle_service, "discover_and_load", blocking_import)

    window.add_subtitle_paths((directory,))
    qtbot.waitUntil(started.is_set, timeout=3000)
    assert window.active_task_kind == "subtitle_import"
    assert window.add_subtitle_directory_button.isEnabled() is False

    window.cancel_active_task()
    release.set()
    qtbot.waitUntil(lambda: window.active_task is None, timeout=3000)

    assert window.subtitle_paths == [existing]
    assert window.task_status.text() == window.translations.text("task.cancelled")
