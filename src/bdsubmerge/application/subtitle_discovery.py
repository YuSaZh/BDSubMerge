"""Discover supported subtitle files in deterministic natural order."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from bdsubmerge.cancellation import CancellationCheck, raise_if_cancelled

SUPPORTED_SUBTITLE_SUFFIXES = frozenset({".ass", ".ssa", ".srt", ".sup"})

_NATURAL_NUMBER = re.compile(r"([0-9]+)")

type NaturalPathKey = tuple[tuple[int, int | str], ...]
type DiscoveryProgress = Callable[[Path], None]
type DiscoveryErrorHandler = Callable[[Path, OSError], None]
type InputDirectoryHandler = Callable[[Path], None]


def natural_path_key(path: Path) -> NaturalPathKey:
    """Return a case-insensitive key that compares embedded numbers numerically."""

    normalized = str(path).replace("\\", "/").casefold()
    return tuple(
        (1, int(part)) if part.isascii() and part.isdigit() else (0, part)
        for part in _NATURAL_NUMBER.split(normalized)
    )


def discover_subtitle_paths(
    inputs: Iterable[Path],
    *,
    cancellation_check: CancellationCheck | None = None,
    progress: DiscoveryProgress | None = None,
    on_error: DiscoveryErrorHandler | None = None,
    on_input_directory: InputDirectoryHandler | None = None,
) -> tuple[Path, ...]:
    """Recursively find supported subtitle files from mixed file and directory inputs."""

    discovered: list[Path] = []
    seen: set[str] = set()
    for input_path in inputs:
        raise_if_cancelled(cancellation_check)
        if progress is not None:
            progress(input_path)
        try:
            is_file = input_path.is_file()
            is_directory = input_path.is_dir()
        except OSError as error:
            if on_error is not None:
                on_error(input_path, error)
            continue
        if is_file:
            _append_candidate(input_path, discovered, seen, on_error=on_error)
            continue
        if not is_directory:
            continue
        if on_input_directory is not None:
            on_input_directory(input_path)

        for root, directory_names, file_names in os.walk(
            input_path,
            onerror=_walk_error_handler(input_path, on_error),
        ):
            raise_if_cancelled(cancellation_check)
            directory = Path(root)
            if progress is not None:
                progress(directory)
            directory_names.sort(key=str.casefold)
            for file_name in file_names:
                raise_if_cancelled(cancellation_check)
                candidate = directory / file_name
                if candidate.suffix.casefold() not in SUPPORTED_SUBTITLE_SUFFIXES:
                    continue
                if progress is not None:
                    progress(candidate)
                _append_candidate(candidate, discovered, seen, on_error=on_error)
    return tuple(sorted(discovered, key=lambda path: (natural_path_key(path), str(path))))


def append_discovered_subtitle_paths(
    existing: Iterable[Path],
    inputs: Iterable[Path],
    *,
    cancellation_check: CancellationCheck | None = None,
    progress: DiscoveryProgress | None = None,
    on_error: DiscoveryErrorHandler | None = None,
    on_input_directory: InputDirectoryHandler | None = None,
) -> tuple[Path, ...]:
    """Preserve the existing order and append only newly discovered subtitles."""

    ordered: list[Path] = []
    seen: set[str] = set()
    for path in (
        *existing,
        *discover_subtitle_paths(
            inputs,
            cancellation_check=cancellation_check,
            progress=progress,
            on_error=on_error,
            on_input_directory=on_input_directory,
        ),
    ):
        raise_if_cancelled(cancellation_check)
        identity = _path_identity(path)
        if identity in seen:
            continue
        seen.add(identity)
        ordered.append(path)
    return tuple(ordered)


def _append_candidate(
    candidate: Path,
    discovered: list[Path],
    seen: set[str],
    *,
    on_error: DiscoveryErrorHandler | None,
) -> None:
    if candidate.suffix.casefold() not in SUPPORTED_SUBTITLE_SUFFIXES:
        return
    try:
        if not candidate.is_file():
            return
    except OSError as error:
        if on_error is not None:
            on_error(candidate, error)
        return
    identity = _path_identity(candidate)
    if identity in seen:
        return
    seen.add(identity)
    discovered.append(candidate)


def _walk_error_handler(
    input_path: Path,
    on_error: DiscoveryErrorHandler | None,
) -> Callable[[OSError], None]:
    def handle(error: OSError) -> None:
        if on_error is None:
            return
        failed_path = Path(error.filename) if error.filename else input_path
        on_error(failed_path, error)

    return handle


def _path_identity(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))
