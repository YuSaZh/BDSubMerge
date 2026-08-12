"""Ordered dynamic-programming episode mapping."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .confidence import classify_confidence, lowest_confidence
from .models import (
    EpisodeMapping,
    EpisodeRequest,
    MappingConfidence,
    MappingCostConfig,
    MappingLock,
    MappingResult,
    MediaTick90k,
    TimelineBoundary,
)


class MappingError(ValueError):
    """The requested mapping constraints have no valid ordered solution."""


@dataclass(frozen=True, slots=True)
class _State:
    cost: int
    path: tuple[tuple[int, int], ...]


def auto_map_episodes(
    episodes: Sequence[EpisodeRequest],
    boundaries: Iterable[TimelineBoundary],
    *,
    locks: Iterable[MappingLock] = (),
    config: MappingCostConfig | None = None,
) -> MappingResult:
    """Choose non-overlapping ordered intervals using dynamic programming.

    Gaps are legal and charged explicitly. Locked intervals remain fixed while all other
    episodes are optimized around them. Equal-cost paths use boundary indices as a stable
    deterministic tie-breaker.
    """

    cost_config = config or MappingCostConfig()
    episode_items = tuple(episodes)
    if not episode_items:
        return MappingResult((), 0, MappingConfidence.HIGH)
    if len({episode.id for episode in episode_items}) != len(episode_items):
        raise MappingError("episode ids must be unique")
    boundary_items = tuple(
        sorted(
            (item for item in boundaries if item.enabled),
            key=lambda item: (int(item.time_90k), item.id),
        )
    )
    if len(boundary_items) < 2:
        raise MappingError("at least two enabled timeline boundaries are required")
    if any(
        int(left.time_90k) == int(right.time_90k)
        for left, right in zip(boundary_items, boundary_items[1:], strict=False)
    ):
        raise MappingError("enabled boundaries must have distinct times; merge them first")

    boundary_index = {item.id: index for index, item in enumerate(boundary_items)}
    if len(boundary_index) != len(boundary_items):
        raise MappingError("boundary ids must be unique")
    lock_by_episode = _validate_locks(episode_items, tuple(locks), boundary_index)

    states: dict[int, _State] = {-1: _State(0, ())}
    for episode in episode_items:
        lock = lock_by_episode.get(episode.id)
        allowed_starts = (
            (boundary_index[lock.start_boundary_id],)
            if lock is not None
            else range(len(boundary_items) - 1)
        )
        next_states: dict[int, _State] = {}
        for start_index in allowed_starts:
            predecessor = _best_predecessor(
                states, start_index, boundary_items, cost_config
            )
            if predecessor is None:
                continue
            allowed_ends = (
                (boundary_index[lock.end_boundary_id],)
                if lock is not None
                else range(start_index + 1, len(boundary_items))
            )
            for end_index in allowed_ends:
                if end_index <= start_index:
                    continue
                interval_cost = _interval_cost(
                    episode,
                    boundary_items[start_index],
                    boundary_items[end_index],
                    cost_config,
                )
                candidate = _State(
                    predecessor.cost + interval_cost,
                    (*predecessor.path, (start_index, end_index)),
                )
                current = next_states.get(end_index)
                if current is None or (candidate.cost, candidate.path) < (
                    current.cost,
                    current.path,
                ):
                    next_states[end_index] = candidate
        if not next_states:
            raise MappingError(
                f"no ordered mapping satisfies constraints at episode {episode.id!r}"
            )
        states = next_states

    ranked = sorted(states.values(), key=lambda state: (state.cost, state.path))
    best = ranked[0]

    mappings: list[EpisodeMapping] = []
    for episode, (start_index, end_index) in zip(episode_items, best.path, strict=True):
        start = boundary_items[start_index]
        end = boundary_items[end_index]
        local_cost = _interval_cost(episode, start, end, cost_config)
        reference = max(int(episode.effective_end_90k), int(end.time_90k) - int(start.time_90k))
        local_alternative = _local_alternative_cost(
            episode, start_index, end_index, boundary_items, cost_config
        )
        confidence = classify_confidence(
            cost=local_cost,
            reference_duration_90k=reference,
            alternative_cost=local_alternative,
            config=cost_config,
        )
        lock = lock_by_episode.get(episode.id)
        warnings: list[str] = []
        if episode.duration_estimated:
            warnings.append("subtitle duration is estimated")
        if confidence is MappingConfidence.LOW:
            warnings.append("automatic mapping requires explicit confirmation")
        mappings.append(
            EpisodeMapping(
                episode_id=episode.id,
                subtitle_ref=episode.subtitle_ref,
                start_boundary=start,
                end_boundary=end,
                manual_offset_90k=(lock.manual_offset_90k if lock else MediaTick90k(0)),
                score=max(0, 100 - local_cost * 100 // max(reference, 1)),
                confidence=confidence,
                locked=lock is not None,
                warnings=tuple(warnings),
            )
        )

    overall = lowest_confidence(tuple(mapping.confidence for mapping in mappings))
    result_warnings = (
        ("one or more automatic mappings require explicit confirmation",)
        if overall is MappingConfidence.LOW
        else ()
    )
    return MappingResult(tuple(mappings), best.cost, overall, result_warnings)


def _validate_locks(
    episodes: tuple[EpisodeRequest, ...],
    locks: tuple[MappingLock, ...],
    boundary_index: dict[str, int],
) -> dict[str, MappingLock]:
    episode_ids = {episode.id for episode in episodes}
    result: dict[str, MappingLock] = {}
    for lock in locks:
        if lock.episode_id not in episode_ids:
            raise MappingError(f"lock refers to unknown episode {lock.episode_id!r}")
        if lock.episode_id in result:
            raise MappingError(f"episode {lock.episode_id!r} has more than one lock")
        try:
            start = boundary_index[lock.start_boundary_id]
            end = boundary_index[lock.end_boundary_id]
        except KeyError as error:
            raise MappingError(f"lock refers to unavailable boundary {error.args[0]!r}") from error
        if end <= start:
            raise MappingError(f"locked interval for {lock.episode_id!r} is not forward")
        result[lock.episode_id] = lock
    return result


def _interval_cost(
    episode: EpisodeRequest,
    start: TimelineBoundary,
    end: TimelineBoundary,
    config: MappingCostConfig,
) -> int:
    duration = int(end.time_90k) - int(start.time_90k)
    subtitle_duration = int(episode.effective_end_90k)
    if subtitle_duration <= duration:
        duration_cost = (duration - subtitle_duration) * config.early_end_weight
    else:
        duration_cost = (subtitle_duration - duration) * config.overrun_weight
    boundary_cost = (
        (200 - start.confidence - end.confidence) * config.boundary_penalty_per_percent
    )
    short_cost = (
        config.short_interval_penalty
        if duration < int(config.short_interval_threshold_90k)
        else 0
    )
    estimated_cost = config.estimated_duration_penalty if episode.duration_estimated else 0
    return duration_cost + boundary_cost + short_cost + estimated_cost


def _gap_cost(gap_90k: int, config: MappingCostConfig) -> int:
    return gap_90k * config.skipped_timeline_weight // config.skipped_timeline_divisor


def _best_predecessor(
    states: dict[int, _State],
    start_index: int,
    boundaries: tuple[TimelineBoundary, ...],
    config: MappingCostConfig,
) -> _State | None:
    start_time = int(boundaries[start_index].time_90k)
    candidates: list[_State] = []
    for previous_end, state in states.items():
        if previous_end > start_index:
            continue
        previous_time = (
            int(boundaries[0].time_90k)
            if previous_end < 0
            else int(boundaries[previous_end].time_90k)
        )
        candidates.append(
            _State(state.cost + _gap_cost(start_time - previous_time, config), state.path)
        )
    return min(candidates, key=lambda item: (item.cost, item.path), default=None)


def _local_alternative_cost(
    episode: EpisodeRequest,
    start_index: int,
    end_index: int,
    boundaries: tuple[TimelineBoundary, ...],
    config: MappingCostConfig,
) -> int | None:
    alternatives: list[int] = []
    for candidate_start, candidate_end in (
        (start_index - 1, end_index),
        (start_index + 1, end_index),
        (start_index, end_index - 1),
        (start_index, end_index + 1),
    ):
        if 0 <= candidate_start < candidate_end < len(boundaries):
            alternatives.append(
                _interval_cost(
                    episode,
                    boundaries[candidate_start],
                    boundaries[candidate_end],
                    config,
                )
            )
    return min(alternatives, default=None)
