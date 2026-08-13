"""Framework-neutral cooperative cancellation shared by background operations."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

type CancellationCheck = Callable[[], bool]
type ProgressReporter = Callable[[int, str], None]


class OperationCancelledError(Exception):
    """Raised at a cooperative checkpoint after cancellation is requested."""


_CURRENT_CHECK: ContextVar[CancellationCheck | None] = ContextVar(
    "bdsubmerge_cancellation_check",
    default=None,
)
_CURRENT_PROGRESS: ContextVar[ProgressReporter | None] = ContextVar(
    "bdsubmerge_progress_reporter",
    default=None,
)


def raise_if_cancelled(check: CancellationCheck | None = None) -> None:
    """Raise when the explicit or task-local cancellation check is set."""

    active_check = check if check is not None else _CURRENT_CHECK.get()
    if active_check is not None and active_check():
        raise OperationCancelledError("operation cancelled")


def report_progress(value: int, detail: str) -> None:
    """Report progress to the active surface without coupling core code to it."""

    reporter = _CURRENT_PROGRESS.get()
    if reporter is not None:
        reporter(max(0, min(100, value)), detail)


@contextmanager
def cancellation_scope(check: CancellationCheck | None) -> Iterator[None]:
    """Make a cancellation check visible to lower layers without changing their callers."""

    if check is None:
        yield
        return
    context_token = _CURRENT_CHECK.set(check)
    try:
        yield
    finally:
        _CURRENT_CHECK.reset(context_token)


@contextmanager
def progress_scope(reporter: ProgressReporter | None) -> Iterator[None]:
    """Make a progress reporter visible to nested application operations."""

    if reporter is None:
        yield
        return
    context_token = _CURRENT_PROGRESS.set(reporter)
    try:
        yield
    finally:
        _CURRENT_PROGRESS.reset(context_token)
