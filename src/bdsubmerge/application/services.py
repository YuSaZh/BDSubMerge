"""Shared application orchestration used by non-interactive and GUI surfaces."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

from bdsubmerge.bdmv import (
    RankingContext,
    rank_playlists,
    resolve_bdmv_layout,
    scan_playlists,
)
from bdsubmerge.domain.models import PlaylistInfo
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.mapping import (
    BoundaryKind,
    BoundarySource,
    EpisodeRequest,
    MappingError,
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
    preflight_outputs,
    write_outputs_atomically,
)
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


class BdmvApplicationService:
    def __init__(self, *, playlist_adapter: PlaylistAdapter | None = None) -> None:
        self._playlist_adapter = playlist_adapter

    def scan(self, request: ScanRequest) -> ScanResult:
        try:
            layout = resolve_bdmv_layout(request.selected_path, max_depth=request.max_depth)
        except (OSError, ValueError) as error:
            return ScanResult(None, (), (_error("bdmv_resolution_failed", str(error)),))
        playlists = scan_playlists(layout, adapter=self._playlist_adapter)
        ranked = rank_playlists(
            playlists,
            RankingContext(
                MediaTick90k(request.subtitle_total_duration_90k)
                if request.subtitle_total_duration_90k is not None
                else None,
                request.subtitle_count,
            ),
        )
        issues: list[ApplicationIssue] = []
        if not ranked:
            issues.append(_error("no_playlists", "no MPLS playlists could be scanned"))
        for playlist in ranked:
            for message in playlist.errors:
                issues.append(_warning("playlist_unavailable", message, str(playlist.path)))
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

    def load_ordered(self, request: LoadSubtitlesRequest) -> LoadSubtitlesResult:
        if not request.sources:
            return LoadSubtitlesResult((), None, (_error("no_subtitles", "no subtitles supplied"),))
        assets: list[SubtitleAsset] = []
        issues: list[ApplicationIssue] = []
        for source in request.sources:
            if source.path.suffix.casefold() == ".sup":
                try:
                    document = parse_sup(self._read_bytes(source.path))
                except (OSError, ValueError) as error:
                    issues.append(_error("subtitle_load_failed", str(error), str(source.path)))
                    continue
                duration = estimate_sup_duration(document)
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
                    issues.append(_warning("sup_structure_warning", warning, str(source.path)))
                continue
            try:
                loaded = load_text_subtitle(
                    self._read_bytes(source.path),
                    name=source.path.name,
                    encoding=source.encoding,
                )
                analysis = analyze_text_subtitle(loaded.document)
            except UnsupportedSubtitleFormatError as error:
                issues.append(_error("unsupported_subtitle_format", str(error), str(source.path)))
                continue
            except (OSError, ValueError) as error:
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

        formats = {asset.format for asset in assets}
        if len(formats) > 1:
            issues.append(
                _error("mixed_subtitle_formats", "all subtitles in a task must use one format")
            )
        subtitle_format = next(iter(formats)) if len(formats) == 1 else None
        return LoadSubtitlesResult(tuple(assets), subtitle_format, tuple(issues))


class MergeApplicationService:
    def prepare(self, request: PrepareMergeRequest) -> PreparedMerge:
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
            boundaries = build_playlist_boundaries(
                request.playlist,
                tolerance_90k=MediaTick90k(request.boundary_tolerance_90k),
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
                locks=request.locks,
                config=request.mapping_config,
            )
        except (MappingError, ValueError) as error:
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
        output_preflight = preflight_outputs(
            request.output_targets,
            context,
            require_existing_sources=request.require_existing_sources,
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
            payload, report = _merge_payload(request, mapping)
        except (MergeConflictError, PgsTimestampOverflowError, TypeError, ValueError) as error:
            issues.append(_error("merge_preflight_failed", str(error)))
            payload = None
            report = None
        if report is not None:
            for notice in report.notices:
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
        return PreparedMerge(mapping, output_preflight, report, payload, tuple(issues))

    def execute(self, request: ExecuteMergeRequest) -> ExecuteMergeResult:
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
        try:
            receipt = write_outputs_atomically(prepared.output_preflight, payloads)
        except (OSError, OutputPreflightError) as error:
            return ExecuteMergeResult(
                prepared,
                False,
                None,
                (_error("output_write_failed", str(error)),),
            )
        return ExecuteMergeResult(prepared, False, receipt)


ZERO_BOUNDARY_TOLERANCE = MediaTick90k(0)


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
    request: PrepareMergeRequest, mapping: MappingResult
) -> tuple[str | bytes, MergeReport]:
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
            )
            for asset, mapped in zip(
                request.subtitles.assets, mapping.mappings, strict=True
            )
        )
        result = merge_ass(MergePlan(sources, options))
        return replace(result.document, bom=False).serialize(), result.report
    if request.subtitles.format is SubtitleFormat.SRT:
        srt_sources = tuple(
            MergeSource(
                asset.path.stem,
                cast(SrtDocument, asset.document),
                int(mapped.final_offset_90k),
            )
            for asset, mapped in zip(
                request.subtitles.assets, mapping.mappings, strict=True
            )
        )
        result = merge_srt(MergePlan(srt_sources, options))
        return result.document.serialize(bom=False), result.report
    if request.subtitles.format is SubtitleFormat.SUP:
        pgs_sources = tuple(
            PgsSource(
                cast(PgsDocument, asset.document),
                mapped.final_offset_90k,
                asset.path.stem,
            )
            for asset, mapped in zip(
                request.subtitles.assets, mapping.mappings, strict=True
            )
        )
        document = append_sup_sources(pgs_sources)
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
        return document.to_bytes(), report
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


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _error(code: str, message: str, source: str | None = None) -> ApplicationIssue:
    return ApplicationIssue(ApplicationSeverity.ERROR, code, message, source)


def _warning(code: str, message: str, source: str | None = None) -> ApplicationIssue:
    return ApplicationIssue(ApplicationSeverity.WARNING, code, message, source)
