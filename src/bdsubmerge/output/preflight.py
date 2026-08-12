"""Transactional preflight for all output destinations."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from .models import (
    CollisionPolicy,
    IssueSeverity,
    OutputContext,
    OutputPreset,
    PreflightIssue,
    PreflightResult,
    ResolvedOutput,
)
from .targets import OutputTarget

_SOURCE_MEDIA_SUFFIXES = frozenset({".bdmv", ".mpls", ".clpi", ".m2ts"})


def preflight_outputs(
    targets: Iterable[OutputTarget],
    context: OutputContext,
    *,
    require_existing_sources: bool = True,
) -> PreflightResult:
    """Resolve and validate every destination before any file is written."""

    target_items = tuple(targets)
    issues: list[PreflightIssue] = []
    outputs: list[ResolvedOutput] = []
    if not target_items:
        issues.append(_error("no_outputs", "at least one output target is required"))
        return PreflightResult((), tuple(issues))
    if len({target.target_id for target in target_items}) != len(target_items):
        issues.append(_error("duplicate_target_id", "output target ids must be unique"))

    jriver_count = sum(target.preset is OutputPreset.JRIVER for target in target_items)
    if jriver_count > 1:
        issues.append(
            _error("multiple_jriver_targets", "one BDMV can have only one JRiver main output")
        )
    if (
        require_existing_sources
        and jriver_count
        and (context.index_bdmv_path is None or not context.index_bdmv_path.is_file())
    ):
        issues.append(
            _error("missing_index_bdmv", "the discovered index.bdmv file no longer exists")
        )

    input_keys = {_path_key(path) for path in context.input_subtitle_paths}
    output_keys: dict[str, str] = {}
    for target in target_items:
        for message in target.validate(context):
            issues.append(_error("invalid_target", message, target.target_id))
        try:
            path = target.resolve_path(context)
        except (KeyError, ValueError) as error:
            issues.append(_error("resolve_failed", str(error), target.target_id))
            continue
        path = _absolute_without_resolving(path)
        if path.suffix.casefold() != f".{context.extension}".casefold():
            issues.append(
                _error(
                    "format_mismatch",
                    f"destination extension must be .{context.extension}",
                    target.target_id,
                    path,
                )
            )
        if path.suffix.casefold() in _SOURCE_MEDIA_SUFFIXES:
            issues.append(
                _error(
                    "source_media_destination",
                    "output cannot overwrite a BDMV source media file",
                    target.target_id,
                    path,
                )
            )
        key = _path_key(path)
        if key in input_keys:
            issues.append(
                _error(
                    "overwrites_input",
                    "output path is the same as an input subtitle",
                    target.target_id,
                    path,
                )
            )
        previous_target = output_keys.get(key)
        if previous_target is not None:
            issues.append(
                _error(
                    "outputs_overlap",
                    f"output path also belongs to target {previous_target!r}",
                    target.target_id,
                    path,
                )
            )
        else:
            output_keys[key] = target.target_id

        parent = path.parent
        if not parent.exists():
            issues.append(
                _error(
                    "missing_output_directory",
                    "output directory does not exist",
                    target.target_id,
                    parent,
                )
            )
        elif not parent.is_dir():
            issues.append(
                _error(
                    "invalid_output_directory",
                    "output parent is not a directory",
                    target.target_id,
                    parent,
                )
            )
        elif not os.access(parent, os.W_OK):
            issues.append(
                _error(
                    "output_directory_not_writable",
                    "output directory is not writable",
                    target.target_id,
                    parent,
                )
            )

        resolved_path = path
        backup_path: Path | None = None
        if path.exists():
            if target.collision_policy is CollisionPolicy.ABORT:
                issues.append(
                    _error(
                        "destination_exists",
                        "destination exists and collision policy is abort",
                        target.target_id,
                        path,
                    )
                )
            elif target.collision_policy is CollisionPolicy.AUTO_RENAME:
                resolved_path = _next_available_name(path, output_keys)
                if previous_target is None:
                    output_keys.pop(key, None)
                output_keys[_path_key(resolved_path)] = target.target_id
                issues.append(
                    _info(
                        "destination_renamed",
                        f"destination renamed to {resolved_path.name}",
                        target.target_id,
                        resolved_path,
                    )
                )
            elif target.collision_policy is CollisionPolicy.BACKUP:
                backup_path = _next_backup_name(path, output_keys)
                output_keys[_path_key(backup_path)] = f"{target.target_id}:backup"
                issues.append(
                    _info(
                        "destination_backup",
                        f"existing destination will be backed up to {backup_path.name}",
                        target.target_id,
                        backup_path,
                    )
                )
            else:
                issues.append(
                    _warning(
                        "destination_overwrite",
                        "existing destination will be overwritten",
                        target.target_id,
                        path,
                    )
                )
        outputs.append(
            ResolvedOutput(
                target_id=target.target_id,
                preset=target.preset,
                path=resolved_path,
                encoding=target.encoding,
                collision_policy=target.collision_policy,
                backup_path=backup_path,
            )
        )
    return PreflightResult(tuple(outputs), tuple(issues))


def _next_available_name(path: Path, reserved: dict[str, str]) -> Path:
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists() and _path_key(candidate) not in reserved:
            return candidate
        counter += 1


def _next_backup_name(path: Path, reserved: dict[str, str]) -> Path:
    candidate = path.with_name(f"{path.name}.bak")
    counter = 1
    while candidate.exists() or _path_key(candidate) in reserved:
        candidate = path.with_name(f"{path.name}.bak.{counter}")
        counter += 1
    return candidate


def _absolute_without_resolving(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.absolute()))


def _error(
    code: str, message: str, target_id: str | None = None, path: Path | None = None
) -> PreflightIssue:
    return PreflightIssue(IssueSeverity.ERROR, code, message, target_id, path)


def _warning(code: str, message: str, target_id: str, path: Path) -> PreflightIssue:
    return PreflightIssue(IssueSeverity.WARNING, code, message, target_id, path)


def _info(code: str, message: str, target_id: str, path: Path) -> PreflightIssue:
    return PreflightIssue(IssueSeverity.INFO, code, message, target_id, path)
