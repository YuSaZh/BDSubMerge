"""Same-filesystem atomic output transactions with rollback and optional backups."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .models import (
    AtomicWriteError,
    CollisionPolicy,
    OutputPreflightError,
    PreflightResult,
    ResolvedOutput,
)

Payload = bytes | str
Validator = Callable[[Path, ResolvedOutput], None]


@dataclass(frozen=True, slots=True)
class WriteReceipt:
    paths: tuple[Path, ...]
    backups: tuple[Path, ...]


def write_outputs_atomically(
    preflight: PreflightResult,
    payloads: Mapping[str, Payload],
    *,
    validator: Validator | None = None,
) -> WriteReceipt:
    """Stage every output, validate all stages, then commit or roll back the whole set."""

    outputs = preflight.require_ready()
    expected_ids = {output.target_id for output in outputs}
    if set(payloads) != expected_ids:
        missing = expected_ids - set(payloads)
        extra = set(payloads) - expected_ids
        raise OutputPreflightError(
            f"payload ids differ from preflight (missing={sorted(missing)}, extra={sorted(extra)})"
        )

    staged: dict[str, Path] = {}
    rollback: dict[str, Path] = {}
    committed: list[ResolvedOutput] = []
    backups: list[Path] = []
    try:
        for output in outputs:
            staged[output.target_id] = _stage(output, payloads[output.target_id])
        for output in outputs:
            stage_path = staged[output.target_id]
            if validator is not None:
                validator(stage_path, output)
            elif not stage_path.is_file():
                raise AtomicWriteError(f"staged output disappeared: {stage_path}")

        # Re-check collision assumptions immediately before moving any existing destination.
        for output in outputs:
            if output.collision_policy in (CollisionPolicy.ABORT, CollisionPolicy.AUTO_RENAME):
                if output.path.exists():
                    raise AtomicWriteError(f"destination appeared after preflight: {output.path}")

        for output in outputs:
            if not output.path.exists():
                continue
            if output.collision_policy is CollisionPolicy.BACKUP:
                if output.backup_path is None or output.backup_path.exists():
                    raise AtomicWriteError(
                        f"backup path is no longer available: {output.backup_path}"
                    )
                output.path.replace(output.backup_path)
                rollback[output.target_id] = output.backup_path
                backups.append(output.backup_path)
            elif output.collision_policy is CollisionPolicy.OVERWRITE:
                rollback_path = _reserve_temp_path(
                    output.path.parent,
                    output.path.name,
                    ".rollback",
                )
                output.path.replace(rollback_path)
                rollback[output.target_id] = rollback_path

        for output in outputs:
            staged[output.target_id].replace(output.path)
            committed.append(output)
            _sync_directory(output.path.parent)
        for output in outputs:
            saved_original = rollback.get(output.target_id)
            if (
                saved_original is not None
                and output.collision_policy is CollisionPolicy.OVERWRITE
            ):
                _safe_unlink(saved_original)
        return WriteReceipt(
            tuple(output.path for output in outputs),
            tuple(backups),
        )
    except Exception as error:
        _rollback(outputs, committed, rollback)
        if isinstance(error, AtomicWriteError | OutputPreflightError):
            raise
        raise AtomicWriteError(f"atomic output transaction failed: {error}") from error
    finally:
        for path in staged.values():
            _safe_unlink(path)
        for output in outputs:
            pending_original = rollback.get(output.target_id)
            if (
                pending_original is not None
                and output.collision_policy is CollisionPolicy.OVERWRITE
            ):
                _safe_unlink(pending_original)


def _stage(output: ResolvedOutput, payload: Payload) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{output.path.name}.", suffix=".tmp", dir=output.path.parent
    )
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            data = payload.encode(output.encoding) if isinstance(payload, str) else payload
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        _safe_unlink(path)
        raise
    return path


def _reserve_temp_path(directory: Path, stem: str, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{stem}.", suffix=suffix, dir=directory)
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    return path


def _rollback(
    outputs: tuple[ResolvedOutput, ...],
    committed: list[ResolvedOutput],
    rollback: dict[str, Path],
) -> None:
    committed_ids = {output.target_id for output in committed}
    for output in reversed(outputs):
        if output.target_id in committed_ids:
            output.path.unlink(missing_ok=True)
        original = rollback.get(output.target_id)
        if original is not None and original.exists():
            original.replace(output.path)


def _sync_directory(directory: Path) -> None:
    """Best-effort directory metadata sync on platforms which expose directory fds."""

    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # Cleanup failure must not turn a completed atomic replacement into a rollback.
        pass
