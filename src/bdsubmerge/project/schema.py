"""Versioned, immutable project-file schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PureWindowsPath

CURRENT_SCHEMA_VERSION = 1


class ProjectSchemaError(ValueError):
    """A project file does not satisfy the supported schema."""


class SourceState(StrEnum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class StoredPath:
    """Portable relative path with an absolute recovery hint."""

    relative: str | None
    absolute: str

    def __post_init__(self) -> None:
        if not self.absolute:
            raise ProjectSchemaError("stored path requires an absolute recovery value")
        if self.relative is not None and (
            Path(self.relative).is_absolute() or PureWindowsPath(self.relative).is_absolute()
        ):
            raise ProjectSchemaError("stored relative path cannot be absolute")

    @property
    def name(self) -> str:
        native = Path(self.absolute).name
        return PureWindowsPath(self.absolute).name if "\\" in native else native


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    """Cheap source identity; never hashes or reads file contents."""

    size: int
    mtime_ns: int

    def __post_init__(self) -> None:
        if self.size < 0 or self.mtime_ns < 0:
            raise ProjectSchemaError("file fingerprint values cannot be negative")


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    path: StoredPath
    fingerprint: FileFingerprint


@dataclass(frozen=True, slots=True)
class PlaylistSnapshot:
    source: FileSnapshot
    stem: str
    duration_90k: int
    timeline_fingerprint: tuple[tuple[str, int, int, int], ...] = ()

    def __post_init__(self) -> None:
        if not self.stem or self.duration_90k < 0:
            raise ProjectSchemaError("playlist stem is required and duration cannot be negative")


@dataclass(frozen=True, slots=True)
class SubtitleSnapshot:
    id: str
    source: FileSnapshot
    format: str
    encoding: str
    order: int
    raw_end_90k: int | None = None
    effective_end_90k: int | None = None
    event_count: int = 0
    style_count: int = 0
    metadata: tuple[tuple[str, str], ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.format or not self.encoding:
            raise ProjectSchemaError("subtitle id, format, and encoding are required")
        if self.order < 0:
            raise ProjectSchemaError("subtitle order cannot be negative")
        if self.raw_end_90k is not None and self.raw_end_90k < 0:
            raise ProjectSchemaError("raw subtitle end cannot be negative")
        if self.effective_end_90k is not None and self.effective_end_90k < 0:
            raise ProjectSchemaError("effective subtitle end cannot be negative")
        if self.event_count < 0 or self.style_count < 0:
            raise ProjectSchemaError("subtitle event and style counts cannot be negative")
        _require_unique("subtitle metadata", tuple(key for key, _ in self.metadata))


@dataclass(frozen=True, slots=True)
class BoundarySnapshot:
    id: str
    time_90k: int
    kinds: tuple[str, ...] = ()
    source_references: tuple[str, ...] = ()
    confidence: int = 100
    enabled: bool = True
    user_created: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if not self.id or self.time_90k < 0:
            raise ProjectSchemaError("boundary id is required and time cannot be negative")
        if not 0 <= self.confidence <= 100:
            raise ProjectSchemaError("boundary confidence must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class MappingSnapshot:
    subtitle_id: str
    start_boundary_id: str
    end_boundary_id: str
    start_90k: int
    end_90k: int
    manual_offset_90k: int = 0
    locked: bool = False
    confidence: str = "low"
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.subtitle_id or not self.start_boundary_id or not self.end_boundary_id:
            raise ProjectSchemaError("mapping references cannot be empty")
        if self.start_90k < 0 or self.end_90k <= self.start_90k:
            raise ProjectSchemaError("mapping interval must be positive")
        if self.confidence not in {"high", "medium", "low"}:
            raise ProjectSchemaError("mapping confidence is invalid")


@dataclass(frozen=True, slots=True)
class OutputSnapshot:
    id: str
    preset: str
    path_template: str
    resolved_path: StoredPath | None
    encoding: str
    collision_policy: str
    backup_policy: str = "none"

    def __post_init__(self) -> None:
        if not self.id or not self.preset or not self.encoding or not self.collision_policy:
            raise ProjectSchemaError(
                "output id, preset, encoding, and collision policy are required"
            )


@dataclass(frozen=True, slots=True)
class ConflictPolicySnapshot:
    accept_script_info_conflicts: bool = False
    keep_events_ending_before_zero: bool = False
    clip_negative_starts: bool = True
    preserve_unknown_sections: bool = True


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    bdmv: FileSnapshot
    index_bdmv: FileSnapshot
    playlist: PlaylistSnapshot
    subtitles: tuple[SubtitleSnapshot, ...]
    boundaries: tuple[BoundarySnapshot, ...]
    mappings: tuple[MappingSnapshot, ...]
    outputs: tuple[OutputSnapshot, ...]
    conflict_policy: ConflictPolicySnapshot = field(default_factory=ConflictPolicySnapshot)
    ui_notes: str = ""
    schema_version: int = CURRENT_SCHEMA_VERSION

    @property
    def bdmv_path(self) -> StoredPath:
        return self.bdmv.path

    def __post_init__(self) -> None:
        if self.schema_version != CURRENT_SCHEMA_VERSION:
            raise ProjectSchemaError(
                f"model schema version must be {CURRENT_SCHEMA_VERSION}, got {self.schema_version}"
            )
        _require_unique("subtitle", tuple(item.id for item in self.subtitles))
        _require_unique("subtitle order", tuple(str(item.order) for item in self.subtitles))
        _require_unique("boundary", tuple(item.id for item in self.boundaries))
        _require_unique("output", tuple(item.id for item in self.outputs))
        _require_unique("mapping subtitle", tuple(item.subtitle_id for item in self.mappings))
        subtitle_ids = {item.id for item in self.subtitles}
        boundary_ids = {item.id for item in self.boundaries}
        if any(mapping.subtitle_id not in subtitle_ids for mapping in self.mappings):
            raise ProjectSchemaError("mapping references an unknown subtitle")
        if any(
            mapping.start_boundary_id not in boundary_ids
            or mapping.end_boundary_id not in boundary_ids
            for mapping in self.mappings
        ):
            raise ProjectSchemaError("mapping references an unknown boundary")


@dataclass(frozen=True, slots=True)
class SourceCheck:
    id: str
    path: Path
    state: SourceState
    expected: FileFingerprint
    actual: FileFingerprint | None


def _require_unique(kind: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ProjectSchemaError(f"duplicate {kind} id")
