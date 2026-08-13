"""Cancelable QThreadPool jobs for application-service calls."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = Event()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()


class TaskSignals(QObject):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str, str)
    cancelled = Signal()
    finished = Signal()


class ServiceTask[ResultT](QRunnable):
    def __init__(
        self,
        operation: Callable[[], ResultT],
        *,
        token: CancellationToken | None = None,
    ) -> None:
        super().__init__()
        self.operation = operation
        self.token = token or CancellationToken()
        self.signals = TaskSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            if self.token.is_cancelled():
                self.signals.cancelled.emit()
                return
            self.signals.progress.emit(5, "started")
            result = self.operation()
            if self.token.is_cancelled():
                self.signals.cancelled.emit()
                return
            self.signals.progress.emit(100, "complete")
            self.signals.succeeded.emit(result)
        except Exception as error:
            self.signals.failed.emit(str(error), traceback.format_exc())
        finally:
            self.signals.finished.emit()
