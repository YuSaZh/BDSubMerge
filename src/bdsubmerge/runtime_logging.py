"""Privacy-preserving structured runtime logging for CLI and GUI entry points."""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "bdsubmerge.runtime"
_DEPENDENCIES = ("pysubs2", "shinya", "PySide6", "PyInstaller")
_LOG_FILE_NAME = "bdsubmerge.jsonl"


class _JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = str(getattr(record, "event", record.getMessage()))
        details = getattr(record, "details", {})
        payload = {
            "timestamp_utc": datetime.fromtimestamp(
                record.created, tz=UTC
            ).isoformat(),
            "level": record.levelname.lower(),
            "event": event,
            "details": details if isinstance(details, dict) else {},
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def default_log_directory(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the platform-standard per-user log directory without touching the filesystem."""

    platform_value = platform_name or sys.platform
    environment = os.environ if environ is None else environ
    home_path = Path.home() if home is None else home
    if platform_value.startswith("win"):
        base = environment.get("LOCALAPPDATA") or environment.get("APPDATA")
        return (Path(base) if base else home_path / "AppData" / "Local") / "BDSubMerge" / "logs"
    if platform_value == "darwin":
        return home_path / "Library" / "Logs" / "BDSubMerge"
    state_home = environment.get("XDG_STATE_HOME")
    base = Path(state_home) if state_home else home_path / ".local" / "state"
    return base / "bdsubmerge" / "logs"


def dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in _DEPENDENCIES:
        try:
            versions[distribution] = version(distribution)
        except PackageNotFoundError:
            versions[distribution] = "not-installed"
    return versions


def configure_runtime_logging(
    directory: Path | None = None,
    *,
    reset: bool = False,
) -> Path | None:
    """Configure one bounded JSONL log in user application data.

    Failure to create the log must not prevent subtitle work. Callers still receive a logger
    backed by ``NullHandler`` when the user profile is not writable.
    """

    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers and not reset:
        handler = next(
            (item for item in logger.handlers if isinstance(item, logging.FileHandler)),
            None,
        )
        return Path(handler.baseFilename) if isinstance(handler, logging.FileHandler) else None
    _clear_handlers(logger)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    log_directory = directory or default_log_directory()
    log_path = log_directory / _LOG_FILE_NAME
    try:
        log_directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError:
        logger.addHandler(logging.NullHandler())
        return None
    handler.setFormatter(_JsonLineFormatter())
    logger.addHandler(handler)
    from bdsubmerge import __version__

    record_runtime_event(
        "runtime_environment",
        application_version=__version__,
        python_version=sys.version.split()[0],
        dependencies=dependency_versions(),
        platform=sys.platform,
    )
    return log_path


def shutdown_runtime_logging() -> None:
    _clear_handlers(logging.getLogger(_LOGGER_NAME))


def record_runtime_event(event: str, **details: object) -> None:
    logging.getLogger(_LOGGER_NAME).info(
        event,
        extra={"event": event, "details": details},
    )


def record_runtime_exception(event: str, error: BaseException, **details: object) -> None:
    """Record an exception type and traceback frames, deliberately omitting its message."""

    stack = tuple(
        {
            "file": frame.filename,
            "line": frame.lineno,
            "function": frame.name,
        }
        for frame in traceback.extract_tb(error.__traceback__)
    )
    record_runtime_event(
        event,
        **details,
        error_type=f"{type(error).__module__}.{type(error).__qualname__}",
        stack=stack,
    )


def _clear_handlers(logger: logging.Logger) -> None:
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
