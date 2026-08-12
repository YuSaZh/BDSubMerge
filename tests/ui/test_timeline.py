from pathlib import Path

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from bdsubmerge.domain.models import PlaylistInfo
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.ui.timeline import TimelineView


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
