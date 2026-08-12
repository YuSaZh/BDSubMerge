from pathlib import Path
from threading import Event

from PySide6.QtCore import QSettings, QThreadPool, Qt
from pytestqt.qtbot import QtBot

from bdsubmerge.ui.main_window import MainWindow
from bdsubmerge.ui.tasks import CancellationToken, ServiceTask


def _settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_service_task_delivers_result(qtbot: QtBot) -> None:
    task: ServiceTask[str] = ServiceTask(lambda: "done")

    with qtbot.waitSignal(task.signals.succeeded, timeout=3000) as signal:
        QThreadPool.globalInstance().start(task)

    assert signal.args == ["done"]


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

    window._start_task(blocking_operation, "blocked", successes.append)
    qtbot.waitUntil(started.is_set, timeout=3000)

    qtbot.mouseClick(window.advanced_toggle, Qt.MouseButton.LeftButton)
    assert window.advanced_toggle.isChecked() is True
    assert window.active_task is not None

    window.cancel_active_task()
    release.set()
    qtbot.waitUntil(lambda: window.active_task is None, timeout=3000)

    assert successes == []
    assert window.cancellation is None
    assert window.task_status.text() == window.translations.text("task.cancelled")
