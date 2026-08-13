import pytest

from bdsubmerge.mapping import (
    BoundaryKind,
    BoundarySource,
    EpisodeRequest,
    MappingConfidence,
    MappingCostConfig,
    MappingError,
    MappingLock,
    MediaTick90k,
    TimelineBoundary,
    auto_map_episodes,
    boundary,
)

SECOND = 90_000
SOURCE = BoundarySource(BoundaryKind.CHAPTER)


def _boundary(boundary_id: str, seconds: int) -> TimelineBoundary:
    return boundary(boundary_id, seconds * SECOND, SOURCE)


def test_dynamic_programming_returns_ordered_non_overlapping_exact_mapping() -> None:
    episodes = (
        EpisodeRequest("e1", MediaTick90k(100 * SECOND), "01.ass"),
        EpisodeRequest("e2", MediaTick90k(100 * SECOND), "02.ass"),
    )
    boundaries = (_boundary("b0", 0), _boundary("b1", 100), _boundary("b2", 200))

    result = auto_map_episodes(episodes, boundaries)

    assert [(item.start_boundary.id, item.end_boundary.id) for item in result.mappings] == [
        ("b0", "b1"),
        ("b1", "b2"),
    ]
    assert result.total_cost == 0
    assert result.confidence is MappingConfidence.HIGH


def test_locked_episode_is_preserved_while_neighbors_are_recomputed() -> None:
    episodes = (
        EpisodeRequest("e1", MediaTick90k(90 * SECOND)),
        EpisodeRequest("e2", MediaTick90k(90 * SECOND)),
        EpisodeRequest("e3", MediaTick90k(90 * SECOND)),
    )
    boundaries = tuple(_boundary(f"b{index}", index * 90) for index in range(4))
    lock = MappingLock("e2", "b1", "b2", MediaTick90k(900))

    result = auto_map_episodes(episodes, boundaries, locks=(lock,))

    middle = result.mappings[1]
    assert middle.locked is True
    assert middle.start_boundary.id == "b1"
    assert middle.end_boundary.id == "b2"
    assert middle.manual_offset_90k == 900
    assert middle.final_offset_90k == 90 * SECOND + 900


def test_conflicting_locked_order_is_rejected() -> None:
    episodes = (
        EpisodeRequest("e1", MediaTick90k(60 * SECOND)),
        EpisodeRequest("e2", MediaTick90k(60 * SECOND)),
    )
    boundaries = tuple(_boundary(f"b{index}", index * 60) for index in range(4))
    locks = (MappingLock("e1", "b2", "b3"), MappingLock("e2", "b0", "b1"))

    with pytest.raises(MappingError, match="no ordered mapping"):
        auto_map_episodes(episodes, boundaries, locks=locks)


def test_overrun_is_penalized_more_than_normal_early_dialogue_end() -> None:
    config = MappingCostConfig(short_interval_threshold_90k=MediaTick90k(0))
    episode = EpisodeRequest("e1", MediaTick90k(95 * SECOND))
    boundaries = (_boundary("b0", 0), _boundary("b1", 90), _boundary("b2", 100))

    result = auto_map_episodes((episode,), boundaries, config=config)

    assert result.mappings[0].end_boundary.id == "b2"


def test_logo_play_item_is_left_as_an_explicit_gap_between_episodes() -> None:
    episodes = (
        EpisodeRequest("e1", MediaTick90k(90 * SECOND)),
        EpisodeRequest("e2", MediaTick90k(90 * SECOND)),
    )
    boundaries = (
        boundary(
            "playlist-start",
            0,
            BoundarySource(BoundaryKind.PLAYLIST_START, "playlist"),
        ),
        boundary(
            "episode-1-end",
            90 * SECOND,
            BoundarySource(BoundaryKind.PLAY_ITEM_END, "episode-1"),
        ),
        boundary(
            "episode-2-start",
            100 * SECOND,
            BoundarySource(BoundaryKind.PLAY_ITEM_START, "episode-2"),
        ),
        boundary(
            "playlist-end",
            190 * SECOND,
            BoundarySource(BoundaryKind.PLAYLIST_END, "playlist"),
        ),
    )

    result = auto_map_episodes(episodes, boundaries)

    assert [(item.start_boundary.id, item.end_boundary.id) for item in result.mappings] == [
        ("playlist-start", "episode-1-end"),
        ("episode-2-start", "playlist-end"),
    ]
    assert result.total_cost == 10 * SECOND // 50


def test_one_episode_can_span_multiple_play_item_boundaries() -> None:
    episode = EpisodeRequest("e1", MediaTick90k(90 * SECOND))
    boundaries = (
        boundary(
            "playlist-start",
            0,
            BoundarySource(BoundaryKind.PLAYLIST_START, "playlist"),
        ),
        boundary(
            "play-item-1-end",
            30 * SECOND,
            BoundarySource(BoundaryKind.PLAY_ITEM_END, "item:0"),
            BoundarySource(BoundaryKind.PLAY_ITEM_START, "item:1"),
        ),
        boundary(
            "play-item-2-end",
            60 * SECOND,
            BoundarySource(BoundaryKind.PLAY_ITEM_END, "item:1"),
            BoundarySource(BoundaryKind.PLAY_ITEM_START, "item:2"),
        ),
        boundary(
            "playlist-end",
            90 * SECOND,
            BoundarySource(BoundaryKind.PLAYLIST_END, "playlist"),
        ),
    )

    result = auto_map_episodes((episode,), boundaries)

    assert result.mappings[0].start_boundary.id == "playlist-start"
    assert result.mappings[0].end_boundary.id == "playlist-end"
    assert result.mappings[0].interval_duration_90k == 90 * SECOND


def test_equal_cost_mapping_uses_stable_earliest_boundary_tie_breaker() -> None:
    episode = EpisodeRequest("e1", MediaTick90k(100 * SECOND))
    boundaries = (_boundary("b0", 0), _boundary("b1", 100), _boundary("b2", 200))
    config = MappingCostConfig(
        skipped_timeline_weight=0,
        short_interval_threshold_90k=MediaTick90k(0),
    )

    forward = auto_map_episodes((episode,), boundaries, config=config)
    reversed_input = auto_map_episodes((episode,), reversed(boundaries), config=config)

    assert forward.total_cost == reversed_input.total_cost == 0
    assert (forward.mappings[0].start_boundary.id, forward.mappings[0].end_boundary.id) == (
        "b0",
        "b1",
    )
    assert reversed_input.mappings[0] == forward.mappings[0]
