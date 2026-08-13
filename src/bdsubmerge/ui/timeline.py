"""Scalable playlist and episode-mapping timeline visualization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import override

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem, QGraphicsScene, QGraphicsView

from bdsubmerge.domain.models import PlaylistInfo
from bdsubmerge.mapping import TimelineBoundary

ITEM_KIND_ROLE = 0
ITEM_ID_ROLE = 1
ITEM_EDGE_ROLE = 2


class TimeDisplayFormat(StrEnum):
    CLOCK = "clock"
    TIMECODE = "timecode"
    TICKS = "ticks"


@dataclass(frozen=True, slots=True)
class TimelineEpisode:
    id: str
    label: str
    start_90k: int
    end_90k: int
    content_start_90k: int
    content_end_90k: int
    confidence: str = "high"
    locked: bool = False
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("timeline episode id cannot be empty")
        if self.end_90k <= self.start_90k:
            raise ValueError("timeline episode interval must be positive")
        if self.content_end_90k <= self.content_start_90k:
            raise ValueError("timeline episode content interval must be positive")


class TimelineView(QGraphicsView):
    user_boundary_added = Signal(str, int)
    user_boundary_moved = Signal(str, int)
    user_boundary_deleted = Signal(str)
    episode_selected = Signal(str)
    episode_boundary_moved = Signal(str, str, int, str)

    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setMinimumHeight(180)
        self.setAccessibleName("timeline")
        self._playlist: PlaylistInfo | None = None
        self._timeline_width = 1_200.0
        self._user_boundaries: dict[str, int] = {}
        self._boundary_items: dict[str, QGraphicsLineItem] = {}
        self._candidate_boundaries: tuple[TimelineBoundary, ...] = ()
        self._episodes: tuple[TimelineEpisode, ...] = ()
        self._selected_episode_id: str | None = None
        self._time_format = TimeDisplayFormat.CLOCK
        self._frame_rate = 24
        self._item_label = "Item"
        self._chapter_label = "Chapter"
        self._empty_text = ""
        self._dragged_item: QGraphicsItem | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def show_playlist(
        self,
        playlist: PlaylistInfo | None,
        *,
        item_label: str,
        chapter_label: str,
        empty_text: str,
    ) -> None:
        self._playlist = playlist
        self._item_label = item_label
        self._chapter_label = chapter_label
        self._empty_text = empty_text
        self._render_scene(fit=True)

    def set_candidate_boundaries(
        self, boundaries: tuple[TimelineBoundary, ...]
    ) -> None:
        self._candidate_boundaries = tuple(
            sorted(boundaries, key=lambda item: (int(item.time_90k), item.id))
        )

    def set_episodes(
        self,
        episodes: tuple[TimelineEpisode, ...],
        *,
        selected_episode_id: str | None = None,
    ) -> None:
        self._episodes = episodes
        self._selected_episode_id = selected_episode_id
        self._render_scene()

    def set_selected_episode(self, episode_id: str | None) -> None:
        if self._selected_episode_id == episode_id:
            return
        self._selected_episode_id = episode_id
        self._render_scene()

    def set_time_format(self, value: TimeDisplayFormat) -> None:
        if self._time_format is value:
            return
        self._time_format = value
        self._render_scene()

    @property
    def time_format(self) -> TimeDisplayFormat:
        return self._time_format

    @property
    def user_boundaries(self) -> tuple[tuple[str, int], ...]:
        return tuple(
            sorted(self._user_boundaries.items(), key=lambda item: (item[1], item[0]))
        )

    @property
    def unmapped_intervals(self) -> tuple[tuple[int, int], ...]:
        if self._playlist is None:
            return ()
        total = int(self._playlist.duration_90k)
        intervals = sorted(
            (
                max(0, episode.start_90k),
                min(total, episode.end_90k),
            )
            for episode in self._episodes
            if episode.end_90k > 0 and episode.start_90k < total
        )
        gaps: list[tuple[int, int]] = []
        cursor = 0
        for start, end in intervals:
            if end <= start:
                continue
            if start > cursor:
                gaps.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < total:
            gaps.append((cursor, total))
        return tuple(gaps)

    @property
    def conflicting_episode_ids(self) -> frozenset[str]:
        conflicts: set[str] = set()
        for index, left in enumerate(self._episodes):
            for right in self._episodes[index + 1 :]:
                if max(left.content_start_90k, right.content_start_90k) < min(
                    left.content_end_90k, right.content_end_90k
                ):
                    conflicts.update((left.id, right.id))
        return frozenset(conflicts)

    def set_user_boundaries(self, boundaries: tuple[tuple[str, int], ...]) -> None:
        self._user_boundaries = dict(boundaries)
        self._render_scene()

    def add_user_boundary(self, time_90k: int, boundary_id: str | None = None) -> str:
        identifier = self._add_user_boundary(time_90k, boundary_id)
        self._render_scene()
        self.user_boundary_added.emit(identifier, self._user_boundaries[identifier])
        return identifier

    def remove_user_boundary(self, boundary_id: str) -> None:
        if boundary_id in self._user_boundaries:
            del self._user_boundaries[boundary_id]
            self._render_scene()
            self.user_boundary_deleted.emit(boundary_id)

    def snap_time(
        self, time_90k: int, *, disabled: bool = False
    ) -> tuple[int, str | None]:
        clamped = self._clamp_ticks(time_90k)
        if disabled:
            return clamped, None
        candidates = (
            *((int(item.time_90k), item.id) for item in self._candidate_boundaries),
            *((time, identifier) for identifier, time in self.user_boundaries),
        )
        if not candidates:
            return clamped, None
        snapped_time, identifier = min(
            candidates,
            key=lambda item: (abs(item[0] - clamped), item[0], item[1]),
        )
        return snapped_time, identifier

    def move_episode_handle(
        self,
        episode_id: str,
        edge: str,
        raw_time_90k: int,
        *,
        snapping_disabled: bool = False,
    ) -> bool:
        time_90k, boundary_id = self.snap_time(
            raw_time_90k,
            disabled=snapping_disabled,
        )
        episode = next(
            (item for item in self._episodes if item.id == episode_id),
            None,
        )
        if (
            episode is None
            or edge not in {"start", "end"}
            or (edge == "start" and time_90k >= episode.end_90k)
            or (edge == "end" and time_90k <= episode.start_90k)
        ):
            self._render_scene()
            return False
        added_user_boundary = False
        if boundary_id is None:
            boundary_id = self._add_user_boundary(time_90k)
            added_user_boundary = True
        self.episode_boundary_moved.emit(
            episode_id,
            edge,
            time_90k,
            boundary_id,
        )
        if added_user_boundary:
            self.user_boundary_added.emit(boundary_id, time_90k)
        return True

    def _render_scene(self, *, fit: bool = False) -> None:
        scene = self.scene()
        scene.clear()
        self._boundary_items.clear()
        playlist = self._playlist
        if playlist is None or int(playlist.duration_90k) <= 0:
            scene.addText(self._empty_text)
            scene.setSceneRect(QRectF(0, 0, 720, 150))
            if fit:
                self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            return

        width = self._timeline_width
        total = int(playlist.duration_90k)
        self._render_play_items(scene, playlist, width, total)
        self._render_unmapped_intervals(scene, width, total)
        self._render_episodes(scene, width, total)
        self._render_user_boundaries(scene, width, total)
        baseline_y = 120
        scene.addLine(0, baseline_y, width, baseline_y, QPen(self.palette().text().color()))
        scene.addText(self._format_time(0)).setPos(0, baseline_y + 1)
        end_label = scene.addText(self._format_time(total))
        end_label.setPos(max(width - 132, 0), baseline_y + 1)
        scene.setSceneRect(QRectF(0, 0, width, 158))
        if fit:
            self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _render_play_items(
        self,
        scene: QGraphicsScene,
        playlist: PlaylistInfo,
        width: float,
        total: int,
    ) -> None:
        for index, item in enumerate(playlist.play_items):
            start = int(item.logical_start_90k) * width / total
            end = int(item.logical_end_90k) * width / total
            color = QColor("#286f9e") if index % 2 == 0 else QColor("#3d8b6d")
            rectangle = scene.addRect(
                start,
                22,
                max(end - start, 2),
                38,
                QPen(Qt.PenStyle.NoPen),
                color,
            )
            rectangle.setToolTip(
                f"{self._item_label} {index + 1}: {item.clip_id} "
                f"({self._format_time(int(item.logical_start_90k))} - "
                f"{self._format_time(int(item.logical_end_90k))})"
            )
            if end - start >= 42:
                label = scene.addText(f"{index + 1}  {item.clip_id}")
                label.setDefaultTextColor(QColor("#ffffff"))
                label.setPos(start + 4, 28)
        chapter_pen = QPen(QColor("#d14545"), 2)
        for mark in playlist.marks:
            if mark.time_90k is None:
                continue
            x = int(mark.time_90k) * width / total
            line = scene.addLine(x, 10, x, 64, chapter_pen)
            line.setToolTip(
                f"{self._chapter_label} {mark.index + 1}: "
                f"{self._format_time(int(mark.time_90k))}"
            )

    def _render_unmapped_intervals(
        self, scene: QGraphicsScene, width: float, total: int
    ) -> None:
        for start_90k, end_90k in self.unmapped_intervals:
            start = start_90k * width / total
            end = end_90k * width / total
            item = scene.addRect(
                start,
                70,
                max(end - start, 1),
                34,
                QPen(QColor("#8a8f98"), 1, Qt.PenStyle.DashLine),
                QColor("#d9dde3"),
            )
            item.setData(ITEM_KIND_ROLE, "unmapped")
            item.setToolTip(
                f"{self._format_time(start_90k)} - {self._format_time(end_90k)}"
            )

    def _render_episodes(
        self, scene: QGraphicsScene, width: float, total: int
    ) -> None:
        conflicts = self.conflicting_episode_ids
        for episode in self._episodes:
            start_90k = max(0, min(episode.start_90k, total))
            end_90k = max(0, min(episode.end_90k, total))
            start = start_90k * width / total
            end = end_90k * width / total
            out_of_bounds = (
                episode.content_start_90k < 0 or episode.content_end_90k > total
            )
            selected = episode.id == self._selected_episode_id
            if episode.id in conflicts or out_of_bounds:
                fill = QColor("#c94a4a")
            elif episode.confidence == "low" or episode.warnings:
                fill = QColor("#d28b28")
            else:
                fill = QColor("#287f63")
            pen = QPen(
                QColor("#111111") if selected else fill.darker(130),
                3 if selected else 1,
            )
            rectangle = scene.addRect(start, 70, max(end - start, 2), 34, pen, fill)
            rectangle.setData(ITEM_KIND_ROLE, "episode")
            rectangle.setData(ITEM_ID_ROLE, episode.id)
            rectangle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            warnings = list(episode.warnings)
            if episode.id in conflicts:
                warnings.append("overlapping subtitle content")
            if out_of_bounds:
                warnings.append("subtitle content exceeds playlist bounds")
            tooltip = (
                f"{episode.label}: {self._format_time(episode.start_90k)} - "
                f"{self._format_time(episode.end_90k)}"
            )
            if warnings:
                tooltip += "\n" + "\n".join(dict.fromkeys(warnings))
            rectangle.setToolTip(tooltip)
            if end - start >= 46:
                label = scene.addText(episode.label[:18])
                label.setDefaultTextColor(QColor("#ffffff"))
                label.setPos(start + 4, 75)
                label.setData(ITEM_KIND_ROLE, "episode")
                label.setData(ITEM_ID_ROLE, episode.id)
            self._add_episode_handle(scene, episode, "start", start)
            self._add_episode_handle(scene, episode, "end", end)

    def _add_episode_handle(
        self,
        scene: QGraphicsScene,
        episode: TimelineEpisode,
        edge: str,
        x: float,
    ) -> None:
        color = (
            QColor("#ffffff")
            if episode.id == self._selected_episode_id
            else QColor("#222222")
        )
        handle = scene.addLine(0, 66, 0, 109, QPen(color, 3))
        handle.setPos(x, 0)
        handle.setData(ITEM_KIND_ROLE, "episode_handle")
        handle.setData(ITEM_ID_ROLE, episode.id)
        handle.setData(ITEM_EDGE_ROLE, edge)
        handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        handle.setToolTip(f"{episode.label}: {edge}")

    def _render_user_boundaries(
        self, scene: QGraphicsScene, width: float, total: int
    ) -> None:
        for boundary_id, time_90k in self.user_boundaries:
            x = time_90k * width / total
            item = scene.addLine(0, 8, 0, 116, QPen(QColor("#f1a12b"), 2))
            item.setPos(x, 0)
            item.setData(ITEM_KIND_ROLE, "user_boundary")
            item.setData(ITEM_ID_ROLE, boundary_id)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            item.setToolTip(f"{boundary_id}: {self._format_time(time_90k)}")
            self._boundary_items[boundary_id] = item

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        item = self.itemAt(event.position().toPoint())
        kind = item.data(ITEM_KIND_ROLE) if item is not None else None
        self._dragged_item = item if kind in {"user_boundary", "episode_handle"} else None
        if item is not None and kind == "episode":
            episode_id = str(item.data(ITEM_ID_ROLE))
            self.episode_selected.emit(episode_id)
        super().mousePressEvent(event)

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._playlist is not None and int(self._playlist.duration_90k) > 0:
            position = self.mapToScene(event.position().toPoint())
            time_90k = int(
                max(0.0, min(position.x(), self._timeline_width))
                * int(self._playlist.duration_90k)
                / self._timeline_width
            )
            self.add_user_boundary(time_90k)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        item = self._dragged_item
        self._dragged_item = None
        if self._playlist is None or item is None or item.scene() is None:
            return
        total = int(self._playlist.duration_90k)
        kind = item.data(ITEM_KIND_ROLE)
        if kind == "user_boundary":
            user_boundary_id = str(item.data(ITEM_ID_ROLE))
            x = max(0.0, min(item.pos().x(), self._timeline_width))
            item.setPos(x, 0)
            time_90k = self._clamp_ticks(int(x * total / self._timeline_width))
            self._user_boundaries[user_boundary_id] = time_90k
            item.setToolTip(
                f"{user_boundary_id}: {self._format_time(time_90k)}"
            )
            self.user_boundary_moved.emit(user_boundary_id, time_90k)
            return
        if kind != "episode_handle":
            return
        episode_id = str(item.data(ITEM_ID_ROLE))
        edge = str(item.data(ITEM_EDGE_ROLE))
        x = max(0.0, min(item.pos().x(), self._timeline_width))
        raw_time = self._clamp_ticks(int(x * total / self._timeline_width))
        self.move_episode_handle(
            episode_id,
            edge,
            raw_time,
            snapping_disabled=bool(
                event.modifiers() & Qt.KeyboardModifier.AltModifier
            ),
        )

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete:
            selected_ids = tuple(
                str(item.data(ITEM_ID_ROLE))
                for item in self.scene().selectedItems()
                if item.data(ITEM_KIND_ROLE) == "user_boundary"
            )
            for boundary_id in selected_ids:
                self.remove_user_boundary(boundary_id)
            event.accept()
            return
        super().keyPressEvent(event)

    def _add_user_boundary(
        self, time_90k: int, boundary_id: str | None = None
    ) -> str:
        identifier = boundary_id or self._next_boundary_id()
        self._user_boundaries[identifier] = self._clamp_ticks(time_90k)
        return identifier

    def _clamp_ticks(self, ticks: int) -> int:
        maximum = (
            int(self._playlist.duration_90k) if self._playlist is not None else ticks
        )
        return max(0, min(ticks, maximum))

    def _next_boundary_id(self) -> str:
        index = 1
        while f"user:{index}" in self._user_boundaries:
            index += 1
        return f"user:{index}"

    def _format_time(self, ticks: int) -> str:
        return format_media_time(ticks, self._time_format, frame_rate=self._frame_rate)

    @override
    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)


def format_media_time(
    ticks: int,
    display_format: TimeDisplayFormat,
    *,
    frame_rate: int = 24,
) -> str:
    if display_format is TimeDisplayFormat.TICKS:
        return str(ticks)
    if display_format is TimeDisplayFormat.TIMECODE:
        if frame_rate <= 0:
            raise ValueError("frame rate must be positive")
        seconds, remainder = divmod(ticks, 90_000)
        hours, remainder_seconds = divmod(seconds, 3_600)
        minutes, seconds = divmod(remainder_seconds, 60)
        frames = remainder * frame_rate // 90_000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"
    milliseconds = ticks // 90
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def format_ticks(ticks: int) -> str:
    return format_media_time(ticks, TimeDisplayFormat.CLOCK)
