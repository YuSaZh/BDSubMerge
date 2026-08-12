"""Deterministic and explainable main-playlist recommendations."""

from __future__ import annotations

from dataclasses import dataclass, replace

from bdsubmerge.domain.models import PlaylistConfidence, PlaylistInfo
from bdsubmerge.domain.timebase import TICKS_PER_SECOND, MediaTick90k

SHORT_ITEM_THRESHOLD = 15 * TICKS_PER_SECOND
FEATURE_LENGTH_THRESHOLD = 20 * 60 * TICKS_PER_SECOND


@dataclass(frozen=True, slots=True)
class RankingContext:
    subtitle_total_duration_90k: MediaTick90k | None = None
    subtitle_count: int | None = None


def _closeness_points(actual: int, expected: int, maximum: int) -> int:
    if expected <= 0:
        return 0
    difference_per_mille = abs(actual - expected) * 1000 // expected
    return max(0, maximum - difference_per_mille * maximum // 500)


def _score(playlist: PlaylistInfo, context: RankingContext) -> tuple[int, tuple[str, ...]]:
    if not playlist.is_available:
        return 0, ("Playlist is unavailable because parsing or validation failed",)

    score = 0
    reasons: list[str] = []
    if playlist.duration_90k >= FEATURE_LENGTH_THRESHOLD:
        score += 25
        reasons.append("Duration exceeds the main-feature threshold")
    else:
        score += min(20, playlist.duration_90k * 20 // FEATURE_LENGTH_THRESHOLD)

    item_count = len(playlist.play_items)
    mark_count = len(playlist.marks)
    if item_count:
        score += min(10, item_count)
        score += min(10, mark_count)
        if playlist.unique_clip_count == item_count:
            score += 15
            reasons.append("Every PlayItem references a unique clip")
        else:
            repeat_penalty = min(20, playlist.repeated_clip_ratio_per_mille * 20 // 1000)
            score -= repeat_penalty
            reasons.append(f"Repeated clip references reduce score by {repeat_penalty}")
        short_items = sum(
            item.duration_90k < SHORT_ITEM_THRESHOLD for item in playlist.play_items
        )
        if short_items:
            penalty = min(20, short_items * 20 // item_count)
            score -= penalty
            reasons.append(f"{short_items} very short PlayItems reduce score by {penalty}")

    if playlist.references_complete:
        score += 10
        reasons.append("All referenced M2TS and CLPI files exist")
    else:
        score -= 20
        reasons.append("Missing referenced M2TS or CLPI files")
    if playlist.has_multi_angle:
        score -= 5
        reasons.append("Multi-angle content requires explicit review")

    if context.subtitle_total_duration_90k is not None:
        points = _closeness_points(
            playlist.duration_90k,
            context.subtitle_total_duration_90k,
            25,
        )
        score += points
        reasons.append(f"Subtitle cumulative duration match contributes {points} points")
    if context.subtitle_count is not None and context.subtitle_count > 0:
        candidates = max(mark_count - 1, item_count)
        points = _closeness_points(candidates, context.subtitle_count, 15)
        score += points
        reasons.append(f"Episode-boundary count match contributes {points} points")
    return max(0, min(100, score)), tuple(reasons)


def _confidence(score: int) -> PlaylistConfidence:
    if score >= 75:
        return PlaylistConfidence.HIGH
    if score >= 45:
        return PlaylistConfidence.MEDIUM
    return PlaylistConfidence.LOW


def rank_playlists(
    playlists: tuple[PlaylistInfo, ...],
    context: RankingContext | None = None,
) -> tuple[PlaylistInfo, ...]:
    """Score and order every playlist without silently selecting one."""
    ranking_context = context or RankingContext()
    ranked: list[PlaylistInfo] = []
    for playlist in playlists:
        score, reasons = _score(playlist, ranking_context)
        ranked.append(
            replace(
                playlist,
                score=score,
                confidence=(
                    _confidence(score) if playlist.is_available else PlaylistConfidence.UNAVAILABLE
                ),
                recommendation_reasons=reasons,
            )
        )
    return tuple(
        sorted(
            ranked,
            key=lambda item: (-item.score, -item.duration_90k, item.stem.casefold()),
        )
    )
