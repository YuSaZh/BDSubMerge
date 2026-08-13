from pathlib import Path

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from bdsubmerge.domain.models import PlaylistInfo
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.mapping import BoundaryKind, BoundarySource, boundary
from bdsubmerge.ui.timeline import (
    TimeDisplayFormat,
    TimelineEpisode,
    TimelineView,
    format_media_time,
)


def _playlist() -> PlaylistInfo:
    return PlaylistInfo(
        path=Path("00001.mpls"),
        stem="00001",
        duration_90k=MediaTick90k(900_000),
        play_items=(),
        marks=(),
    )


def test_user_boundary_can_be_added_moved_and_deleted(qtbot: QtBot) -> None:
    timeline = TimelineView()
    qtbot.addWidget(timeline)
    timeline.show_playlist(
        _playlist(), item_label="Item", chapter_label="Chapter", empty_text="Empty"
    )

    with qtbot.waitSignal(timeline.user_boundary_added) as added:
        boundary_id = timeline.add_user_boundary(450_000)

    assert added.args == [boundary_id, 450_000]
    assert timeline.user_boundaries == ((boundary_id, 450_000),)

    item = timeline._boundary_items[boundary_id]
    item.setSelected(True)
    with qtbot.waitSignal(timeline.user_boundary_deleted):
        qtbot.keyClick(timeline, Qt.Key.Key_Delete)

    assert timeline.user_boundaries == ()


def test_project_boundaries_can_be_restored(qtbot: QtBot) -> None:
    timeline = TimelineView()
    qtbot.addWidget(timeline)
    timeline.show_playlist(
        _playlist(), item_label="Item", chapter_label="Chapter", empty_text="Empty"
    )

    timeline.set_user_boundaries((("user:9", 123_456),))

    assert timeline.user_boundaries == (("user:9", 123_456),)


def test_time_display_formats_use_integer_media_ticks() -> None:
    ticks = 135_000

    assert format_media_time(ticks, TimeDisplayFormat.CLOCK) == "00:00:01.500"
    assert (
        format_media_time(ticks, TimeDisplayFormat.TIMECODE, frame_rate=24)
        == "00:00:01:12"
    )
    assert format_media_time(ticks, TimeDisplayFormat.TICKS) == "135000"


def test_episode_intervals_expose_gaps_conflicts_and_out_of_bounds(
    qtbot: QtBot,
) -> None:
    timeline = TimelineView()
    qtbot.addWidget(timeline)
    timeline.show_playlist(
        _playlist(), item_label="Item", chapter_label="Chapter", empty_text="Empty"
    )
    timeline.set_episodes(
        (
            TimelineEpisode(
                "episode-1",
                "01.ass",
                90_000,
                360_000,
                90_000,
                405_000,
            ),
            TimelineEpisode(
                "episode-2",
                "02.ass",
                450_000,
                720_000,
                360_000,
                990_000,
                confidence="low",
            ),
        )
    )

    assert timeline.unmapped_intervals == (
        (0, 90_000),
        (360_000, 450_000),
        (720_000, 900_000),
    )
    assert timeline.conflicting_episode_ids == frozenset(
        {"episode-1", "episode-2"}
    )
    assert any(
        "exceeds playlist bounds" in item.toolTip()
        for item in timeline.scene().items()
    )


def test_candidate_snapping_is_deterministic_and_can_be_disabled(
    qtbot: QtBot,
) -> None:
    timeline = TimelineView()
    qtbot.addWidget(timeline)
    timeline.show_playlist(
        _playlist(), item_label="Item", chapter_label="Chapter", empty_text="Empty"
    )
    timeline.set_candidate_boundaries(
        (
            boundary(
                "chapter:2",
                360_000,
                BoundarySource(BoundaryKind.CHAPTER, "2"),
            ),
            boundary(
                "play-item:1:end",
                540_000,
                BoundarySource(BoundaryKind.PLAY_ITEM_END, "1"),
            ),
        )
    )

    assert timeline.snap_time(400_000) == (360_000, "chapter:2")
    assert timeline.snap_time(400_000, disabled=True) == (400_000, None)


def test_invalid_episode_handle_move_rolls_back_without_orphan_boundary(
    qtbot: QtBot,
) -> None:
    timeline = TimelineView()
    qtbot.addWidget(timeline)
    timeline.show_playlist(
        _playlist(), item_label="Item", chapter_label="Chapter", empty_text="Empty"
    )
    timeline.set_episodes(
        (
            TimelineEpisode(
                "episode-1",
                "01.ass",
                90_000,
                360_000,
                90_000,
                360_000,
            ),
        )
    )
    moved: list[tuple[str, str, int, str]] = []
    added: list[tuple[str, int]] = []
    timeline.episode_boundary_moved.connect(
        lambda episode_id, edge, ticks, boundary_id: moved.append(
            (episode_id, edge, ticks, boundary_id)
        )
    )
    timeline.user_boundary_added.connect(
        lambda boundary_id, ticks: added.append((boundary_id, ticks))
    )

    accepted = timeline.move_episode_handle(
        "episode-1",
        "start",
        450_000,
        snapping_disabled=True,
    )

    assert accepted is False
    assert timeline.user_boundaries == ()
    assert moved == []
    assert added == []
