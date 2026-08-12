"""Typed request and result models for shared CLI/GUI application services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from bdsubmerge.domain.models import BdmvLayout, PlaylistInfo
from bdsubmerge.mapping import MappingCostConfig, MappingLock, MappingResult
from bdsubmerge.merge import MergeOptions, MergeReport
from bdsubmerge.output import (
    OutputContext,
    OutputTarget,
    PreflightResult,
    WriteReceipt,
)
from bdsubmerge.subtitles import (
    AssDocument,
    PgsDocument,
    SrtDocument,
    SubtitleFormat,
    TextSubtitleInfo,
)


class ApplicationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ApplicationIssue:
    severity: ApplicationSeverity
    code: str
    message: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class ScanRequest:
    selected_path: Path
    max_depth: int = 4
    subtitle_total_duration_90k: int | None = None
    subtitle_count: int | None = None


@dataclass(frozen=True, slots=True)
class ScanResult:
    layout: BdmvLayout | None
    playlists: tuple[PlaylistInfo, ...]
    issues: tuple[ApplicationIssue, ...] = ()

    @property
    def ready(self) -> bool:
        return self.layout is not None and not _has_errors(self.issues)


@dataclass(frozen=True, slots=True)
class InspectRequest:
    scan: ScanResult
    playlist_stem: str


@dataclass(frozen=True, slots=True)
class InspectResult:
    playlist: PlaylistInfo | None
    issues: tuple[ApplicationIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class SubtitleInput:
    path: Path
    encoding: str | None = None


@dataclass(frozen=True, slots=True)
class SubtitleAsset:
    path: Path
    format: SubtitleFormat
    document: AssDocument | SrtDocument | PgsDocument
    analysis: TextSubtitleInfo
    encoding: str | None = None
    bom: bool = False


@dataclass(frozen=True, slots=True)
class LoadSubtitlesRequest:
    sources: tuple[SubtitleInput, ...]


@dataclass(frozen=True, slots=True)
class LoadSubtitlesResult:
    assets: tuple[SubtitleAsset, ...]
    format: SubtitleFormat | None
    issues: tuple[ApplicationIssue, ...] = ()

    @property
    def ready(self) -> bool:
        return bool(self.assets) and self.format is not None and not _has_errors(self.issues)


@dataclass(frozen=True, slots=True)
class PrepareMergeRequest:
    layout: BdmvLayout
    playlist: PlaylistInfo
    subtitles: LoadSubtitlesResult
    output_targets: tuple[OutputTarget, ...]
    output_context: OutputContext | None = None
    locks: tuple[MappingLock, ...] = ()
    mapping_config: MappingCostConfig | None = None
    merge_options: MergeOptions | None = None
    boundary_tolerance_90k: int = 0
    accept_low_confidence: bool = False
    require_existing_sources: bool = True


@dataclass(frozen=True, slots=True)
class PreparedMerge:
    mapping: MappingResult | None
    output_preflight: PreflightResult | None
    report: MergeReport | None
    payload: str | bytes | None
    issues: tuple[ApplicationIssue, ...]

    @property
    def ready(self) -> bool:
        return (
            self.mapping is not None
            and self.output_preflight is not None
            and self.output_preflight.ready
            and self.report is not None
            and self.payload is not None
            and not _has_errors(self.issues)
        )


@dataclass(frozen=True, slots=True)
class ExecuteMergeRequest:
    prepared: PreparedMerge
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class ExecuteMergeResult:
    prepared: PreparedMerge
    dry_run: bool
    receipt: WriteReceipt | None
    issues: tuple[ApplicationIssue, ...] = ()

    @property
    def succeeded(self) -> bool:
        return not _has_errors(self.issues) and (self.dry_run or self.receipt is not None)


def _has_errors(issues: tuple[ApplicationIssue, ...]) -> bool:
    return any(issue.severity is ApplicationSeverity.ERROR for issue in issues)
