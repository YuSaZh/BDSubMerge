"""Shared application orchestration used by non-interactive and GUI surfaces."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from bdsubmerge import __version__
from bdsubmerge.bdmv import (
    RankingContext,
    rank_playlists,
    resolve_bdmv_layout,
    scan_playlists,
)
from bdsubmerge.cancellation import (
    CancellationCheck,
    raise_if_cancelled,
    report_progress,
)
from bdsubmerge.domain.models import PlaylistInfo
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.mapping import (
    BoundaryKind,
    BoundarySource,
    EpisodeRequest,
    MappingError,
    MappingLock,
    MappingResult,
    TimelineBoundary,
    auto_map_episodes,
    boundary,
    merge_boundaries,
)
from bdsubmerge.merge import (
    MergeConflictError,
    MergeNotice,
    MergeOptions,
    MergePlan,
    MergeReport,
    MergeSource,
    merge_ass,
    merge_srt,
)
from bdsubmerge.output import (
    OutputContext,
    OutputPreflightError,
    PreflightResult,
    ResolvedOutput,
    preflight_outputs,
    write_outputs_atomically,
)
from bdsubmerge.runtime_logging import record_runtime_event, record_runtime_exception
from bdsubmerge.subtitles import (
    AssDocument,
    PgsDocument,
    PgsSource,
    SrtDocument,
    SubtitleFormat,
    TextSubtitleInfo,
    analyze_text_subtitle,
    append_sup_sources,
    estimate_sup_duration,
    load_text_subtitle,
    parse_sup,
)
from bdsubmerge.subtitles.loader import UnsupportedSubtitleFormatError
from bdsubmerge.subtitles.pgs_adapter import PgsTimestampOverflowError

from .models import (
    ApplicationIssue,
    ApplicationSeverity,
    ExecuteMergeRequest,
    ExecuteMergeResult,
    ImportSubtitlesRequest,
    ImportSubtitlesResult,
    InspectRequest,
    InspectResult,
    LoadSubtitlesRequest,
    LoadSubtitlesResult,
    PreparedMerge,
    PrepareMergeRequest,
    ScanRequest,
    ScanResult,
    SubtitleAsset,
)
from .protocols import BinaryReader, PlaylistAdapter
from .reporting import (
    REPORT_TARGET_ID,
    MergeExecutionReport,
    ReportEpisode,
    ReportNotice,
    ReportPlayItem,
    ReportPlaylist,
    ReportSourceFingerprint,
    ReportStyleRename,
    preflight_merge_report,
)
from .subtitle_discovery import (
    append_discovered_subtitle_paths,
    discover_subtitle_paths,
)


class BdmvApplicationService:
    def __init__(self, *, playlist_adapter: PlaylistAdapter | None = None) -> None:
        self._playlist_adapter = playlist_adapter

    def scan(
        self,
        request: ScanRequest,
        *,
        cancellation_check: CancellationCheck | None = None,
    ) -> ScanResult:
        raise_if_cancelled(cancellation_check)
        report_progress(10, str(request.selected_path))
        record_runtime_event(
            "bdmv_scan_started",
            selected_path=str(request.selected_path),
            max_depth=request.max_depth,
        )
        try:
            layout = resolve_bdmv_layout(request.selected_path, max_depth=request.max_depth)
        except (OSError, ValueError) as error:
            record_runtime_exception(
                "bdmv_scan_failed",
                error,
                selected_path=str(request.selected_path),
            )
            return ScanResult(None, (), (_error("bdmv_resolution_failed", str(error)),))
        raise_if_cancelled(cancellation_check)
        playlists = scan_playlists(
            layout,
            adapter=self._playlist_adapter,
            cancellation_check=cancellation_check,
        )
        raise_if_cancelled(cancellation_check)
        report_progress(90, str(layout.index_bdmv_path))
        ranked = rank_playlists(
            playlists,
            RankingContext(
                MediaTick90k(request.subtitle_total_duration_90k)
                if request.subtitle_total_duration_90k is not None
                else None,
                request.subtitle_count,
            ),
        )
        raise_if_cancelled(cancellation_check)
        issues: list[ApplicationIssue] = []
        if not ranked:
            issues.append(_error("no_playlists", "no MPLS playlists could be scanned"))
        for playlist in ranked:
            for message in playlist.errors:
                issues.append(_warning("playlist_unavailable", message, str(playlist.path)))
        record_runtime_event(
            "bdmv_scan_completed",
            bdmv_path=str(layout.bdmv_path),
            index_bdmv_path=str(layout.index_bdmv_path),
            playlists=tuple(
                {
                    "path": str(playlist.path),
                    "stem": playlist.stem,
                    "duration_90k": int(playlist.duration_90k),
                    "available": playlist.is_available,
                }
                for playlist in ranked
            ),
        )
        return ScanResult(layout, ranked, tuple(issues))

    def inspect(self, request: InspectRequest) -> InspectResult:
        matches = tuple(
            item
            for item in request.scan.playlists
            if item.stem.casefold() == request.playlist_stem.casefold()
        )
        if not matches:
            return InspectResult(
                None,
                (
                    _error(
                        "playlist_not_found",
                        f"playlist {request.playlist_stem!r} was not scanned",
                    ),
                ),
            )
        if len(matches) > 1:
            return InspectResult(
                None,
                (_error("playlist_ambiguous", f"playlist {request.playlist_stem!r} is ambiguous"),),
            )
        playlist = matches[0]
        issues = tuple(
            _warning("playlist_warning", message, str(playlist.path))
            for message in (*playlist.errors, *playlist.warnings)
        )
        return InspectResult(playlist, issues)


class SubtitleApplicationService:
    def __init__(self, *, read_bytes: BinaryReader | None = None) -> None:
        self._read_bytes = read_bytes or _read_bytes

    def load_ordered(
        self,
        request: LoadSubtitlesRequest,
        *,
        cancellation_check: CancellationCheck | None = None,
    ) -> LoadSubtitlesResult:
        raise_if_cancelled(cancellation_check)
        record_runtime_event(
            "subtitle_load_started",
            sources=tuple(str(source.path) for source in request.sources),
        )
        if not request.sources:
            return LoadSubtitlesResult((), None, (_error("no_subtitles", "no subtitles supplied"),))
        assets: list[SubtitleAsset] = []
        issues: list[ApplicationIssue] = []
        source_count = len(request.sources)
        for index, source in enumerate(request.sources):
            raise_if_cancelled(cancellation_check)
            report_progress(25 + (index * 70 // source_count), str(source.path))
            if source.path.suffix.casefold() == ".sup":
                try:
                    data = self._read_bytes(source.path)
                    raise_if_cancelled(cancellation_check)
                    document = parse_sup(
                        data,
                        cancellation_check=cancellation_check,
                    )
                except (OSError, ValueError) as error:
                    record_runtime_exception(
                        "subtitle_load_failed",
                        error,
                        source_path=str(source.path),
                    )
                    issues.append(_error("subtitle_load_failed", str(error), str(source.path)))
                    continue
                duration = estimate_sup_duration(
                    document,
                    cancellation_check=cancellation_check,
                )
                effective_end = duration.effective_end_90k
                if effective_end is None or effective_end <= 0:
                    issues.append(
                        _error(
                            "subtitle_has_no_duration",
                            "SUP has no positive presentation timestamp",
                            str(source.path),
                        )
                    )
                    continue
                analysis = TextSubtitleInfo(
                    event_count=len(document.packets),
                    style_count=0,
                    earliest_start_ticks=duration.earliest_pts_90k,
                    raw_end_ticks=duration.raw_end_90k,
                    effective_end_ticks=duration.effective_end_90k,
                    suspected_long_tail=False,
                    duration_estimated=duration.estimated,
                )
                assets.append(
                    SubtitleAsset(source.path, SubtitleFormat.SUP, document, analysis)
                )
                if duration.estimated:
                    issues.append(
                        _warning(
                            "sup_duration_estimated",
                            "SUP duration is estimated from packet timestamps",
                            str(source.path),
                        )
                    )
                for warning in document.warnings:
                    raise_if_cancelled(cancellation_check)
                    issues.append(_warning("sup_structure_warning", warning, str(source.path)))
                continue
            try:
                data = self._read_bytes(source.path)
                raise_if_cancelled(cancellation_check)
                loaded = load_text_subtitle(
                    data,
                    name=source.path.name,
                    encoding=source.encoding,
                    cancellation_check=cancellation_check,
                )
                analysis = analyze_text_subtitle(
                    loaded.document,
                    cancellation_check=cancellation_check,
                )
            except UnsupportedSubtitleFormatError as error:
                record_runtime_exception(
                    "subtitle_load_failed",
                    error,
                    source_path=str(source.path),
                )
                issues.append(_error("unsupported_subtitle_format", str(error), str(source.path)))
                continue
            except (OSError, ValueError) as error:
                record_runtime_exception(
                    "subtitle_load_failed",
                    error,
                    source_path=str(source.path),
                )
                issues.append(_error("subtitle_load_failed", str(error), str(source.path)))
                continue
            if analysis.effective_end_ticks is None or analysis.effective_end_ticks <= 0:
                issues.append(
                    _error(
                        "subtitle_has_no_duration",
                        "subtitle has no positive effective duration",
                        str(source.path),
                    )
                )
                continue
            if analysis.suspected_long_tail:
                issues.append(
                    _warning(
                        "subtitle_long_tail",
                        "effective duration excludes a suspected long-tail event",
                        str(source.path),
                    )
                )
            assets.append(
                SubtitleAsset(
                    source.path,
                    loaded.format,
                    loaded.document,
                    analysis,
                    loaded.encoding,
                    loaded.bom,
                )
            )
            raise_if_cancelled(cancellation_check)

        raise_if_cancelled(cancellation_check)
        formats = {asset.format for asset in assets}
        if len(formats) > 1:
            issues.append(
                _error("mixed_subtitle_formats", "all subtitles in a task must use one format")
            )
        subtitle_format = next(iter(formats)) if len(formats) == 1 else None
        record_runtime_event(
            "subtitle_load_completed",
            format=subtitle_format.value if subtitle_format is not None else None,
            sources=tuple(
                {
                    "path": str(asset.path),
                    "format": asset.format.value,
                    "encoding": asset.encoding,
                    "event_count": asset.analysis.event_count,
                    "raw_end_90k": asset.analysis.raw_end_ticks,
                    "effective_end_90k": asset.analysis.effective_end_ticks,
                }
                for asset in assets
            ),
            issue_codes=tuple(issue.code for issue in issues),
        )
        report_progress(95, str(request.sources[-1].path))
        return LoadSubtitlesResult(tuple(assets), subtitle_format, tuple(issues))

    def discover_and_load(
        self,
        request: ImportSubtitlesRequest,
        *,
        cancellation_check: CancellationCheck | None = None,
    ) -> ImportSubtitlesResult:
        """Discover directory inputs and load the resulting ordered subtitle set."""

        discovery_issues: list[ApplicationIssue] = []
        input_directories: list[Path] = []

        def record_discovery_error(path: Path, error: OSError) -> None:
            discovery_issues.append(
                _warning("subtitle_discovery_failed", str(error), str(path))
            )

        def report_current_path(path: Path) -> None:
            report_progress(10, str(path))

        discovered = discover_subtitle_paths(
            request.inputs,
            cancellation_check=cancellation_check,
            progress=report_current_path,
            on_error=record_discovery_error,
            on_input_directory=input_directories.append,
        )
        scan_candidate = next(
            (
                path
                for path in request.inputs
                if path in input_directories
                or path.suffix.casefold() in {".bdmv", ".mpls"}
            ),
            None,
        )
        updated_paths = append_discovered_subtitle_paths(
            request.existing_paths,
            discovered,
            cancellation_check=cancellation_check,
        )
        changed = updated_paths != request.existing_paths
        if not changed:
            return ImportSubtitlesResult(
                updated_paths,
                None,
                False,
                bool(discovered),
                tuple(input_directories),
                tuple(discovery_issues),
                scan_candidate,
            )
        subtitles = self.load_ordered(
            LoadSubtitlesRequest(tuple(SubtitleInput(path) for path in updated_paths)),
            cancellation_check=cancellation_check,
        )
        return ImportSubtitlesResult(
            updated_paths,
            subtitles,
            True,
            bool(discovered),
            tuple(input_directories),
            tuple(discovery_issues),
            scan_candidate,
        )


class MergeApplicationService:
    def prepare(
        self,
        request: PrepareMergeRequest,
        *,
        cancellation_check: CancellationCheck | None = None,
    ) -> PreparedMerge:
        raise_if_cancelled(cancellation_check)
        report_progress(10, str(request.playlist.path))
        record_runtime_event(
            "merge_prepare_started",
            bdmv_path=str(request.layout.bdmv_path),
            playlist_path=str(request.playlist.path),
            playlist_stem=request.playlist.stem,
            subtitle_paths=tuple(str(asset.path) for asset in request.subtitles.assets),
        )
        issues: list[ApplicationIssue] = []
        if request.require_existing_sources:
            issues.extend(_source_existence_issues(request))
        if not request.playlist.is_available:
            issues.append(_error("playlist_unavailable", "selected playlist is unavailable"))
        if not request.subtitles.ready:
            issues.extend(request.subtitles.issues)
            issues.append(_error("subtitles_not_ready", "ordered subtitles are not ready"))
        if issues:
            return PreparedMerge(None, None, None, None, tuple(issues))

        try:
            raise_if_cancelled(cancellation_check)
            tolerance_90k = MediaTick90k(request.boundary_tolerance_90k)
            automatic_boundaries = build_playlist_boundaries(
                request.playlist,
                tolerance_90k=tolerance_90k,
            )
            _validate_additional_boundaries(
                request.additional_boundaries,
                request.playlist,
            )
            boundaries = merge_boundaries(
                (*automatic_boundaries, *request.additional_boundaries),
                tolerance_90k=tolerance_90k,
            )
            locks = _canonicalize_boundary_locks(
                request.locks,
                (*automatic_boundaries, *request.additional_boundaries),
                boundaries,
                tolerance_90k,
            )
            episode_requests = tuple(
                EpisodeRequest(
                    id=f"episode-{index + 1}",
                    effective_end_90k=MediaTick90k(
                        _required_effective_end(asset, index)
                    ),
                    subtitle_ref=str(asset.path),
                    duration_estimated=(
                        asset.analysis.suspected_long_tail
                        or asset.analysis.duration_estimated
                    ),
                )
                for index, asset in enumerate(request.subtitles.assets)
            )
            mapping = auto_map_episodes(
                episode_requests,
                boundaries,
                locks=locks,
                config=request.mapping_config,
            )
            raise_if_cancelled(cancellation_check)
        except (MappingError, ValueError) as error:
            record_runtime_exception(
                "merge_mapping_failed",
                error,
                playlist_path=str(request.playlist.path),
            )
            return PreparedMerge(
                None, None, None, None, (_error("mapping_failed", str(error)),)
            )
        if mapping.has_low_confidence and not request.accept_low_confidence:
            issues.append(
                _error(
                    "low_mapping_confidence",
                    "low-confidence automatic mapping requires explicit confirmation",
                )
            )

        context = request.output_context or _output_context(request)
        raise_if_cancelled(cancellation_check)
        report_progress(25, str(request.playlist.path))
        output_preflight = preflight_outputs(
            request.output_targets,
            context,
            require_existing_sources=request.require_existing_sources,
        )
        raise_if_cancelled(cancellation_check)
        if request.report_target is not None and any(
            target.target_id == REPORT_TARGET_ID for target in request.output_targets
        ):
            issues.append(
                _error(
                    "reserved_report_target_id",
                    f"output target id {REPORT_TARGET_ID!r} is reserved for merge reports",
                )
            )
        for issue in output_preflight.issues:
            severity = (
                ApplicationSeverity.ERROR
                if issue.severity.value == "error"
                else ApplicationSeverity.WARNING
                if issue.severity.value == "warning"
                else ApplicationSeverity.INFO
            )
            issues.append(
                ApplicationIssue(severity, f"output_{issue.code}", issue.message, issue.target_id)
            )

        try:
            payload, report = _merge_payload(
                request,
                mapping,
                cancellation_check=cancellation_check,
            )
            raise_if_cancelled(cancellation_check)
        except (MergeConflictError, PgsTimestampOverflowError, TypeError, ValueError) as error:
            record_runtime_exception(
                "merge_payload_failed",
                error,
                playlist_path=str(request.playlist.path),
            )
            issues.append(_error("merge_preflight_failed", str(error)))
            payload = None
            report = None
        if report is not None:
            for notice in report.notices:
                raise_if_cancelled(cancellation_check)
                severity = (
                    ApplicationSeverity.ERROR
                    if notice.severity == "error"
                    else ApplicationSeverity.WARNING
                    if notice.severity == "warning"
                    else ApplicationSeverity.INFO
                )
                issues.append(
                    ApplicationIssue(
                        severity,
                        f"merge_{notice.code}",
                        notice.message,
                        notice.source_label,
                    )
                )
        execution_report: MergeExecutionReport | None = None
        report_preflight: PreflightResult | None = None
        report_payload: str | None = None
        if report is not None and request.report_target is not None:
            raise_if_cancelled(cancellation_check)
            report_preflight = preflight_merge_report(
                request.report_target,
                bdmv_path=request.layout.bdmv_path,
                source_paths=(
                    request.layout.index_bdmv_path,
                    request.playlist.path,
                    *(asset.path for asset in request.subtitles.assets),
                ),
                subtitle_outputs=output_preflight.outputs,
            )
            raise_if_cancelled(cancellation_check)
            issues.extend(_preflight_application_issues(report_preflight, "report"))
            if report_preflight.outputs:
                execution_report = _execution_report(
                    request,
                    mapping,
                    report,
                    output_preflight.outputs,
                    report_preflight.outputs[0].path,
                    tuple(issues),
                )
                report_payload = execution_report.serialize(
                    request.report_target.report_format
                )
                raise_if_cancelled(cancellation_check)
        progress_path = (
            output_preflight.outputs[0].path
            if output_preflight.outputs
            else request.playlist.path
        )
        report_progress(95, str(progress_path))
        record_runtime_event(
            "merge_prepared",
            playlist_path=str(request.playlist.path),
            mappings=tuple(
                {
                    "episode_id": item.episode_id,
                    "subtitle_path": item.subtitle_ref,
                    "start_90k": int(item.start_boundary.time_90k),
                    "end_90k": int(item.end_boundary.time_90k),
                    "manual_adjustment_90k": int(item.manual_offset_90k),
                    "final_offset_90k": int(item.final_offset_90k),
                    "confidence": item.confidence.value,
                }
                for item in mapping.mappings
            ),
            output_paths=tuple(str(item.path) for item in output_preflight.outputs),
            report_path=(
                str(report_preflight.outputs[0].path)
                if report_preflight is not None and report_preflight.outputs
                else None
            ),
            style_renames=tuple(
                {
                    "source": item.source_label,
                    "old_name": item.old_name,
                    "new_name": item.new_name,
                }
                for item in report.style_renames
            )
            if report is not None
            else (),
            attachment_deduplicated_count=(
                report.attachment_deduplicated_count if report is not None else 0
            ),
            out_of_bounds_event_count=(
                _out_of_bounds_count(report) if report is not None else 0
            ),
            conflict_codes=tuple(
                item.code for item in output_preflight.issues if "destination" in item.code
            ),
            issue_codes=tuple(issue.code for issue in issues),
        )
        return PreparedMerge(
            mapping,
            output_preflight,
            report,
            payload,
            tuple(issues),
            execution_report,
            report_preflight,
            report_payload,
        )

    def execute(
        self,
        request: ExecuteMergeRequest,
        *,
        cancellation_check: CancellationCheck | None = None,
    ) -> ExecuteMergeResult:
        raise_if_cancelled(cancellation_check)
        prepared = request.prepared
        if not prepared.ready:
            return ExecuteMergeResult(
                prepared,
                request.dry_run,
                None,
                (_error("merge_not_ready", "merge preflight contains blocking errors"),),
            )
        if request.dry_run:
            return ExecuteMergeResult(prepared, True, None)
        assert prepared.output_preflight is not None
        assert prepared.payload is not None
        payloads = {
            output.target_id: prepared.payload
            for output in prepared.output_preflight.outputs
        }
        combined_preflight = prepared.output_preflight
        if prepared.report_preflight is not None:
            assert prepared.report_payload is not None
            combined_preflight = PreflightResult(
                (*prepared.output_preflight.outputs, *prepared.report_preflight.outputs),
                (*prepared.output_preflight.issues, *prepared.report_preflight.issues),
            )
            payloads[REPORT_TARGET_ID] = prepared.report_payload
        try:
            receipt = write_outputs_atomically(
                combined_preflight,
                payloads,
                cancellation_check=cancellation_check,
            )
        except (OSError, OutputPreflightError) as error:
            record_runtime_exception(
                "merge_write_failed",
                error,
                output_paths=tuple(
                    str(output.path) for output in combined_preflight.outputs
                ),
            )
            return ExecuteMergeResult(
                prepared,
                False,
                None,
                (_error("output_write_failed", str(error)),),
            )
        record_runtime_event(
            "merge_write_completed",
            output_paths=tuple(str(path) for path in receipt.paths),
            backup_paths=tuple(str(path) for path in receipt.backups),
        )
        return ExecuteMergeResult(prepared, False, receipt)


ZERO_BOUNDARY_TOLERANCE = MediaTick90k(0)


def _validate_additional_boundaries(
    boundaries: tuple[TimelineBoundary, ...],
    playlist: PlaylistInfo,
) -> None:
    duration_90k = int(playlist.duration_90k)
    for item in boundaries:
        if item.kinds != frozenset({BoundaryKind.USER}):
            raise ValueError(
                f"additional boundary {item.id!r} must have only a user source"
            )
        if not 0 <= int(item.time_90k) <= duration_90k:
            raise ValueError(
                f"additional boundary {item.id!r} is outside the playlist timeline"
            )


def _canonicalize_boundary_locks(
    locks: tuple[MappingLock, ...],
    original: tuple[TimelineBoundary, ...],
    normalized: tuple[TimelineBoundary, ...],
    tolerance_90k: MediaTick90k,
) -> tuple[MappingLock, ...]:
    """Translate lock IDs when boundary normalization merges coincident candidates."""

    original_by_id = {item.id: item for item in original}
    normalized_ids = {item.id for item in normalized}
    aliases: dict[str, str] = {}
    tolerance = int(tolerance_90k)
    for boundary_id, item in original_by_id.items():
        if boundary_id in normalized_ids:
            aliases[boundary_id] = boundary_id
            continue
        item_sources = set(item.sources)
        for candidate in normalized:
            delta = int(item.time_90k) - int(candidate.time_90k)
            if 0 <= delta <= tolerance and item_sources.issubset(candidate.sources):
                aliases[boundary_id] = candidate.id
                break

    return tuple(
        replace(
            lock,
            start_boundary_id=aliases.get(lock.start_boundary_id, lock.start_boundary_id),
            end_boundary_id=aliases.get(lock.end_boundary_id, lock.end_boundary_id),
        )
        for lock in locks
    )


def build_playlist_boundaries(
    playlist: PlaylistInfo,
    *,
    tolerance_90k: MediaTick90k = ZERO_BOUNDARY_TOLERANCE,
) -> tuple[TimelineBoundary, ...]:
    candidates: list[TimelineBoundary] = [
        boundary(
            "playlist:start",
            0,
            BoundarySource(BoundaryKind.PLAYLIST_START, playlist.stem),
        ),
        boundary(
            "playlist:end",
            int(playlist.duration_90k),
            BoundarySource(BoundaryKind.PLAYLIST_END, playlist.stem),
        ),
    ]
    for item in playlist.play_items:
        reference = f"play_item:{item.index}:{item.clip_id}"
        candidates.extend(
            (
                boundary(
                    f"item:{item.index}:start",
                    int(item.logical_start_90k),
                    BoundarySource(BoundaryKind.PLAY_ITEM_START, reference),
                    confidence=95,
                ),
                boundary(
                    f"item:{item.index}:end",
                    int(item.logical_end_90k),
                    BoundarySource(BoundaryKind.PLAY_ITEM_END, reference),
                    confidence=95,
                ),
            )
        )
    for mark in playlist.marks:
        if mark.time_90k is not None:
            candidates.append(
                boundary(
                    f"chapter:{mark.index}",
                    int(mark.time_90k),
                    BoundarySource(BoundaryKind.CHAPTER, f"mark:{mark.index}"),
                    confidence=90,
                )
            )
    return merge_boundaries(candidates, tolerance_90k=tolerance_90k)


def _merge_payload(
    request: PrepareMergeRequest,
    mapping: MappingResult,
    *,
    cancellation_check: CancellationCheck | None = None,
) -> tuple[str | bytes, MergeReport]:
    raise_if_cancelled(cancellation_check)
    options = request.merge_options or MergeOptions(
        playlist_end_ticks=int(request.playlist.duration_90k)
    )
    if options.playlist_end_ticks is None:
        options = replace(options, playlist_end_ticks=int(request.playlist.duration_90k))
    if request.subtitles.format in {SubtitleFormat.ASS, SubtitleFormat.SSA}:
        sources = tuple(
            MergeSource(
                asset.path.stem,
                cast(AssDocument, asset.document),
                int(mapped.final_offset_90k),
                str(asset.path),
            )
            for asset, mapped in zip(
                request.subtitles.assets, mapping.mappings, strict=True
            )
        )
        ass_result = merge_ass(
            MergePlan(sources, options),
            cancellation_check=cancellation_check,
        )
        payload = replace(ass_result.document, bom=False).serialize(
            cancellation_check=cancellation_check
        )
        return payload, ass_result.report
    if request.subtitles.format is SubtitleFormat.SRT:
        srt_sources = tuple(
            MergeSource(
                asset.path.stem,
                cast(SrtDocument, asset.document),
                int(mapped.final_offset_90k),
                str(asset.path),
            )
            for asset, mapped in zip(
                request.subtitles.assets, mapping.mappings, strict=True
            )
        )
        srt_result = merge_srt(
            MergePlan(srt_sources, options),
            cancellation_check=cancellation_check,
        )
        return (
            srt_result.document.serialize(
                bom=False,
                cancellation_check=cancellation_check,
            ),
            srt_result.report,
        )
    if request.subtitles.format is SubtitleFormat.SUP:
        pgs_sources = tuple(
            PgsSource(
                cast(PgsDocument, asset.document),
                mapped.final_offset_90k,
                asset.path.stem,
                str(asset.path),
            )
            for asset, mapped in zip(
                request.subtitles.assets, mapping.mappings, strict=True
            )
        )
        document = append_sup_sources(
            pgs_sources,
            cancellation_check=cancellation_check,
        )
        report = MergeReport(
            source_labels=tuple(source.label for source in pgs_sources),
            input_event_count=sum(len(source.document.packets) for source in pgs_sources),
            output_event_count=len(document.packets),
            notices=tuple(
                MergeNotice("warning", "sup_structure_warning", warning)
                for warning in document.warnings
            ),
            metadata={"format": "sup", "duration_estimated": True},
        )
        return document.to_bytes(cancellation_check=cancellation_check), report
    raise ValueError("unsupported or unresolved subtitle format")


def _output_context(request: PrepareMergeRequest) -> OutputContext:
    assert request.subtitles.format is not None
    return OutputContext(
        subtitle_format=request.subtitles.format.value,
        index_bdmv_path=request.layout.index_bdmv_path,
        playlist_path=request.playlist.path,
        disc_container_path=request.layout.disc_container_path,
        input_subtitle_paths=tuple(asset.path for asset in request.subtitles.assets),
    )


def _required_effective_end(asset: SubtitleAsset, index: int) -> int:
    value = asset.analysis.effective_end_ticks
    if value is None:
        raise ValueError(f"subtitle {index + 1} has no effective duration")
    return value


def _source_existence_issues(request: PrepareMergeRequest) -> tuple[ApplicationIssue, ...]:
    checks = (
        (request.layout.bdmv_path.is_dir(), "missing_bdmv", request.layout.bdmv_path),
        (
            request.layout.index_bdmv_path.is_file(),
            "missing_index_bdmv",
            request.layout.index_bdmv_path,
        ),
        (request.playlist.path.is_file(), "missing_playlist", request.playlist.path),
        *(
            (asset.path.is_file(), "missing_subtitle_source", asset.path)
            for asset in request.subtitles.assets
        ),
    )
    return tuple(
        _error(code, f"required source no longer exists: {path}", str(path))
        for exists, code, path in checks
        if not exists
    )


def _preflight_application_issues(
    preflight: PreflightResult,
    prefix: str,
) -> tuple[ApplicationIssue, ...]:
    return tuple(
        ApplicationIssue(
            ApplicationSeverity.ERROR
            if issue.severity.value == "error"
            else ApplicationSeverity.WARNING
            if issue.severity.value == "warning"
            else ApplicationSeverity.INFO,
            f"{prefix}_{issue.code}",
            issue.message,
            issue.target_id,
        )
        for issue in preflight.issues
    )


def _execution_report(
    request: PrepareMergeRequest,
    mapping: MappingResult,
    merge_report: MergeReport,
    outputs: tuple[ResolvedOutput, ...],
    report_path: Path,
    issues: tuple[ApplicationIssue, ...],
) -> MergeExecutionReport:
    episodes = tuple(
        ReportEpisode(
            episode_id=mapped.episode_id,
            subtitle_path=str(asset.path),
            start_90k=int(mapped.start_boundary.time_90k),
            end_90k=int(mapped.end_boundary.time_90k),
            manual_adjustment_90k=int(mapped.manual_offset_90k),
            final_offset_90k=int(mapped.final_offset_90k),
            raw_end_90k=asset.analysis.raw_end_ticks,
            effective_end_90k=_required_effective_end(asset, index),
            event_count=asset.analysis.event_count,
            confidence=mapped.confidence.value,
            locked=mapped.locked,
            warnings=mapped.warnings,
        )
        for index, (asset, mapped) in enumerate(
            zip(request.subtitles.assets, mapping.mappings, strict=True)
        )
    )
    merge_warnings = tuple(
        ReportNotice(item.severity, item.code, item.message, item.source_label)
        for item in merge_report.notices
        if item.severity != "info"
    )
    application_warnings = tuple(
        ReportNotice(item.severity.value, item.code, item.message, item.source)
        for item in issues
        if item.severity is ApplicationSeverity.WARNING
        and not item.code.startswith("merge_")
    )
    return MergeExecutionReport(
        schema_version=1,
        generated_at_utc=datetime.now(UTC).isoformat(),
        application_version=__version__,
        playlist=ReportPlaylist(
            request.playlist.stem,
            str(request.playlist.path),
            int(request.playlist.duration_90k),
            request.playlist.timeline_fingerprint,
        ),
        play_items=tuple(
            ReportPlayItem(
                item.index,
                item.clip_id,
                item.codec_id,
                item.in_time_45k,
                item.out_time_45k,
                int(item.logical_start_90k),
                int(item.logical_end_90k),
                item.connection_condition,
                item.selected_angle,
            )
            for item in request.playlist.play_items
        ),
        episodes=episodes,
        output_paths=tuple(str(output.path) for output in outputs),
        report_path=str(report_path),
        input_event_count=merge_report.input_event_count,
        output_event_count=merge_report.output_event_count,
        dropped_event_count=merge_report.dropped_event_count,
        clipped_event_count=merge_report.clipped_event_count,
        attachment_deduplicated_count=merge_report.attachment_deduplicated_count,
        out_of_bounds_event_count=_out_of_bounds_count(merge_report),
        conflict_count=_conflict_count(merge_report, issues),
        style_renames=tuple(
            ReportStyleRename(item.source_label, item.old_name, item.new_name)
            for item in merge_report.style_renames
        ),
        warnings=(*merge_warnings, *application_warnings),
        source_fingerprints=(
            _source_fingerprint("index_bdmv", "index_bdmv", request.layout.index_bdmv_path),
            _source_fingerprint("playlist", request.playlist.stem, request.playlist.path),
            *(
                _source_fingerprint("subtitle", f"episode-{index + 1}", asset.path)
                for index, asset in enumerate(request.subtitles.assets)
            ),
        ),
    )


def _source_fingerprint(role: str, source_id: str, path: Path) -> ReportSourceFingerprint:
    try:
        stat = path.stat()
    except OSError:
        return ReportSourceFingerprint(role, source_id, str(path), None, None)
    return ReportSourceFingerprint(role, source_id, str(path), stat.st_size, stat.st_mtime_ns)


def _out_of_bounds_count(report: MergeReport) -> int:
    codes = {
        "event_dropped_before_zero",
        "event_start_clipped",
        "event_starts_after_playlist",
        "event_ends_after_playlist",
        "cue_dropped_before_zero",
        "cue_start_clipped",
        "cue_outside_playlist",
    }
    return sum(item.code in codes for item in report.notices)


def _conflict_count(
    report: MergeReport,
    issues: tuple[ApplicationIssue, ...],
) -> int:
    merge_conflicts = sum("conflict" in item.code for item in report.notices)
    output_conflicts = sum(
        item.code
        in {
            "output_destination_exists",
            "output_destination_overwrite",
            "output_outputs_overlap",
            "report_destination_exists",
            "report_destination_overwrite",
            "report_overwrites_input",
        }
        for item in issues
    )
    return merge_conflicts + output_conflicts


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _error(code: str, message: str, source: str | None = None) -> ApplicationIssue:
    return ApplicationIssue(ApplicationSeverity.ERROR, code, message, source)


def _warning(code: str, message: str, source: str | None = None) -> ApplicationIssue:
    return ApplicationIssue(ApplicationSeverity.WARNING, code, message, source)
