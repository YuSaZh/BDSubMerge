"""Discover supported subtitle files in deterministic natural order."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path

SUPPORTED_SUBTITLE_SUFFIXES = frozenset({".ass", ".ssa", ".srt", ".sup"})

_NATURAL_NUMBER = re.compile(r"([0-9]+)")

type NaturalPathKey = tuple[tuple[int, int | str], ...]


def natural_path_key(path: Path) -> NaturalPathKey:
    """Return a case-insensitive key that compares embedded numbers numerically."""

    normalized = str(path).replace("\\", "/").casefold()
    return tuple(
        (1, int(part)) if part.isascii() and part.isdigit() else (0, part)
        for part in _NATURAL_NUMBER.split(normalized)
    )


def discover_subtitle_paths(inputs: Iterable[Path]) -> tuple[Path, ...]:
    """Recursively find supported subtitle files from mixed file and directory inputs."""

    discovered: list[Path] = []
    seen: set[str] = set()
    for input_path in inputs:
        candidates: Iterable[Path]
        if input_path.is_file():
            candidates = (input_path,)
        elif input_path.is_dir():
            candidates = input_path.rglob("*")
        else:
            continue
        for candidate in candidates:
            if (
                candidate.suffix.casefold() not in SUPPORTED_SUBTITLE_SUFFIXES
                or not candidate.is_file()
            ):
                continue
            identity = _path_identity(candidate)
            if identity in seen:
                continue
            seen.add(identity)
            discovered.append(candidate)
    return tuple(sorted(discovered, key=lambda path: (natural_path_key(path), str(path))))


def append_discovered_subtitle_paths(
    existing: Iterable[Path],
    inputs: Iterable[Path],
) -> tuple[Path, ...]:
    """Preserve the existing order and append only newly discovered subtitles."""

    ordered: list[Path] = []
    seen: set[str] = set()
    for path in (*existing, *discover_subtitle_paths(inputs)):
        identity = _path_identity(path)
        if identity in seen:
            continue
        seen.add(identity)
        ordered.append(path)
    return tuple(ordered)


def _path_identity(path: Path) -> str:
    absolute = str(path.resolve(strict=False))
    return absolute.casefold() if os.name == "nt" else absolute
