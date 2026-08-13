"""Execution-level merge reports shared by CLI and GUI application services."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from bdsubmerge.output import (
    CollisionPolicy,
    FullPathOutputTarget,
    IssueSeverity,
    OutputContext,
    PreflightIssue,
    PreflightResult,
    ResolvedOutput,
    preflight_outputs,
)

REPORT_TARGET_ID = "__bdsubmerge_merge_report__"


class MergeReportFormat(StrEnum):
    JSON = "json"
    TEXT = "text"

    @property
    def extension(self) -> str:
        return "json" if self is MergeReportFormat.JSON else "txt"


@dataclass(frozen=True, slots=True)
class MergeReportTarget:
    path: Path
    report_format: MergeReportFormat
    collision_policy: CollisionPolicy = CollisionPolicy.ABORT
    protected_paths: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportSourceFingerprint:
    role: str
    source_id: str
    path: str
    size: int | None
    modified_ns: int | None


@dataclass(frozen=True, slots=True)
class ReportPlaylist:
    stem: str
    path: str
    duration_90k: int
    timeline_fingerprint: tuple[tuple[str, int, int, int], ...]


@dataclass(frozen=True, slots=True)
class ReportPlayItem:
    index: int
    clip_id: str
    codec_id: str
    in_time_45k: int
    out_time_45k: int
    logical_start_90k: int
    logical_end_90k: int
    connection_condition: int
    selected_angle: int


@dataclass(frozen=True, slots=True)
class ReportEpisode:
    episode_id: str
    subtitle_path: str
    start_90k: int
    end_90k: int
    manual_adjustment_90k: int
    final_offset_90k: int
    raw_end_90k: int | None
    effective_end_90k: int
    event_count: int
    confidence: str
    locked: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReportStyleRename:
    source_label: str
    old_name: str
    new_name: str


@dataclass(frozen=True, slots=True)
class ReportNotice:
    severity: str
    code: str
    message: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class MergeExecutionReport:
    schema_version: int
    generated_at_utc: str
    application_version: str
    playlist: ReportPlaylist
    play_items: tuple[ReportPlayItem, ...]
    episodes: tuple[ReportEpisode, ...]
    output_paths: tuple[str, ...]
    report_path: str
    input_event_count: int
    output_event_count: int
    dropped_event_count: int
    clipped_event_count: int
    attachment_deduplicated_count: int
    out_of_bounds_event_count: int
    conflict_count: int
    style_renames: tuple[ReportStyleRename, ...]
    warnings: tuple[ReportNotice, ...]
    source_fingerprints: tuple[ReportSourceFingerprint, ...]

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        ) + "\n"

    def to_text(self) -> str:
        lines = [
            "BDSubMerge merge report",
            f"schema_version: {self.schema_version}",
            f"generated_at_utc: {self.generated_at_utc}",
            f"application_version: {self.application_version}",
            "",
            "Playlist",
            f"stem: {self.playlist.stem}",
            f"path: {self.playlist.path}",
            f"duration_90k: {self.playlist.duration_90k}",
            f"timeline_fingerprint: {json.dumps(self.playlist.timeline_fingerprint)}",
            "",
            "PlayItem timeline",
        ]
        lines.extend(
            "- "
            f"index={item.index} clip={item.clip_id} codec={item.codec_id} "
            f"source_45k={item.in_time_45k}..{item.out_time_45k} "
            f"logical_90k={item.logical_start_90k}..{item.logical_end_90k} "
            f"connection={item.connection_condition} angle={item.selected_angle}"
            for item in self.play_items
        )
        lines.extend(("", "Episodes"))
        lines.extend(
            "- "
            f"id={episode.episode_id} source={episode.subtitle_path} "
            f"interval_90k={episode.start_90k}..{episode.end_90k} "
            f"manual_adjustment_90k={episode.manual_adjustment_90k} "
            f"final_offset_90k={episode.final_offset_90k} "
            f"raw_end_90k={episode.raw_end_90k} "
            f"effective_end_90k={episode.effective_end_90k} "
            f"events={episode.event_count} confidence={episode.confidence} "
            f"locked={str(episode.locked).lower()}"
            for episode in self.episodes
        )
        lines.extend(("", "Outputs"))
        lines.extend(f"- {path}" for path in self.output_paths)
        lines.append(f"report: {self.report_path}")
        lines.extend(
            (
                "",
                "Counts",
                f"input_events: {self.input_event_count}",
                f"output_events: {self.output_event_count}",
                f"dropped_events: {self.dropped_event_count}",
                f"clipped_events: {self.clipped_event_count}",
                f"attachment_deduplicated: {self.attachment_deduplicated_count}",
                f"out_of_bounds_events: {self.out_of_bounds_event_count}",
                f"conflicts: {self.conflict_count}",
                "",
                "Style renames",
            )
        )
        lines.extend(
            f"- source={item.source_label} old={item.old_name} new={item.new_name}"
            for item in self.style_renames
        )
        lines.extend(("", "Warnings"))
        lines.extend(
            f"- [{item.severity}] {item.code}: {item.message}"
            + (f" (source={item.source})" if item.source else "")
            for item in self.warnings
        )
        lines.extend(("", "Source fingerprints"))
        lines.extend(
            "- "
            f"role={item.role} id={item.source_id} path={item.path} "
            f"size={item.size} modified_ns={item.modified_ns}"
            for item in self.source_fingerprints
        )
        return "\n".join(lines) + "\n"

    def serialize(self, report_format: MergeReportFormat) -> str:
        if report_format is MergeReportFormat.JSON:
            return self.to_json()
        return self.to_text()


def preflight_merge_report(
    target: MergeReportTarget,
    *,
    bdmv_path: Path,
    source_paths: tuple[Path, ...],
    subtitle_outputs: tuple[ResolvedOutput, ...],
) -> PreflightResult:
    """Preflight a report as a non-media artifact before any output is staged."""

    protected_paths = (
        *source_paths,
        *target.protected_paths,
        *(output.path for output in subtitle_outputs),
        *(output.backup_path for output in subtitle_outputs if output.backup_path is not None),
    )
    preflight = preflight_outputs(
        (
            FullPathOutputTarget(
                REPORT_TARGET_ID,
                collision_policy=target.collision_policy,
                encoding="utf-8",
                path=target.path,
            ),
        ),
        OutputContext(
            subtitle_format=target.report_format.extension,
            input_subtitle_paths=protected_paths,
        ),
        require_existing_sources=False,
    )
    issues = list(preflight.issues)
    protected_keys = {_path_key(path) for path in protected_paths}
    for output in preflight.outputs:
        if _path_within(output.path, bdmv_path):
            issues.append(
                PreflightIssue(
                    IssueSeverity.ERROR,
                    "inside_bdmv",
                    "merge report cannot be written inside the read-only BDMV tree",
                    REPORT_TARGET_ID,
                    output.path,
                )
            )
        if output.backup_path is not None and _path_key(output.backup_path) in protected_keys:
            issues.append(
                PreflightIssue(
                    IssueSeverity.ERROR,
                    "backup_overlaps_source",
                    "merge report backup path overlaps a source or subtitle output",
                    REPORT_TARGET_ID,
                    output.backup_path,
                )
            )
    return PreflightResult(preflight.outputs, tuple(issues))


def _path_within(path: Path, directory: Path) -> bool:
    path_value = _path_key(path)
    directory_value = _path_key(directory)
    try:
        return os.path.commonpath((path_value, directory_value)) == directory_value
    except ValueError:
        return False


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.absolute()))
