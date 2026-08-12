"""Output destination models shared by CLI and GUI application services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class OutputPreset(StrEnum):
    JRIVER = "jriver"
    PLAYLIST = "playlist"
    DISC_NAME = "disc_name"
    CUSTOM = "custom"
    FULL_PATH = "full_path"


class CollisionPolicy(StrEnum):
    ABORT = "abort"
    OVERWRITE = "overwrite"
    BACKUP = "backup"
    AUTO_RENAME = "auto_rename"


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class OutputContext:
    subtitle_format: str
    index_bdmv_path: Path | None = None
    playlist_path: Path | None = None
    disc_container_path: Path | None = None
    language: str = ""
    volume: str = ""
    input_subtitle_paths: tuple[Path, ...] = ()

    @property
    def extension(self) -> str:
        value = self.subtitle_format.lower().lstrip(".")
        if not value or any(character in value for character in "/\\:"):
            raise ValueError("subtitle format must be a file extension")
        return value

    @property
    def variables(self) -> dict[str, str]:
        playlist_stem = self.playlist_path.stem if self.playlist_path else ""
        index_stem = self.index_bdmv_path.stem if self.index_bdmv_path else ""
        disc_name = self.disc_container_path.name if self.disc_container_path else ""
        return {
            "disc_name": disc_name,
            "playlist": self.playlist_path.name if self.playlist_path else "",
            "playlist_stem": playlist_stem,
            "index_stem": index_stem,
            "language": self.language,
            "format": self.extension,
            "volume": self.volume,
        }


@dataclass(frozen=True, slots=True)
class ResolvedOutput:
    target_id: str
    preset: OutputPreset
    path: Path
    encoding: str
    collision_policy: CollisionPolicy
    backup_path: Path | None = None


@dataclass(frozen=True, slots=True)
class PreflightIssue:
    severity: IssueSeverity
    code: str
    message: str
    target_id: str | None = None
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class PreflightResult:
    outputs: tuple[ResolvedOutput, ...]
    issues: tuple[PreflightIssue, ...]

    @property
    def errors(self) -> tuple[PreflightIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is IssueSeverity.ERROR)

    @property
    def warnings(self) -> tuple[PreflightIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is IssueSeverity.WARNING)

    @property
    def ready(self) -> bool:
        return not self.errors

    def require_ready(self) -> tuple[ResolvedOutput, ...]:
        if self.errors:
            details = "; ".join(f"{issue.code}: {issue.message}" for issue in self.errors)
            raise OutputPreflightError(details)
        return self.outputs


class OutputPreflightError(ValueError):
    """One or more output targets failed transactional preflight."""


class AtomicWriteError(OSError):
    """A prepared output transaction could not be committed."""
