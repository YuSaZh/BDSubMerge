"""Framework-neutral cooperative cancellation shared by background operations."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

type CancellationCheck = Callable[[], bool]


class OperationCancelledError(Exception):
    """Raised at a cooperative checkpoint after cancellation is requested."""


_CURRENT_CHECK: ContextVar[CancellationCheck | None] = ContextVar(
    "bdsubmerge_cancellation_check",
    default=None,
)


def raise_if_cancelled(check: CancellationCheck | None = None) -> None:
    """Raise when the explicit or task-local cancellation check is set."""

    active_check = check if check is not None else _CURRENT_CHECK.get()
    if active_check is not None and active_check():
        raise OperationCancelledError("operation cancelled")


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
