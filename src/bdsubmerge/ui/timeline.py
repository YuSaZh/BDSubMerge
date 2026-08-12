"""Read-only scalable playlist timeline visualization."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem, QGraphicsScene, QGraphicsView

from bdsubmerge.domain.models import PlaylistInfo


class TimelineView(QGraphicsView):
    user_boundary_added = Signal(str, int)
    user_boundary_moved = Signal(str, int)
    user_boundary_deleted = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setMinimumHeight(150)
        self.setAccessibleName("timeline")
        self._playlist: PlaylistInfo | None = None
        self._timeline_width = 1_200.0
        self._user_boundaries: dict[str, int] = {}
        self._boundary_items: dict[str, QGraphicsLineItem] = {}
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def show_playlist(
        self,
        playlist: PlaylistInfo | None,
        *,
        item_label: str,
        chapter_label: str,
        empty_text: str,
    ) -> None:
        scene = self.scene()
        scene.clear()
        self._playlist = playlist
        self._boundary_items.clear()
        if playlist is None or int(playlist.duration_90k) <= 0:
            scene.addText(empty_text)
            scene.setSceneRect(QRectF(0, 0, 720, 120))
            return
        width = self._timeline_width
        total = int(playlist.duration_90k)
        for index, item in enumerate(playlist.play_items):
            start = int(item.logical_start_90k) * width / total
            end = int(item.logical_end_90k) * width / total
            color = QColor("#286f9e") if index % 2 == 0 else QColor("#3d8b6d")
            rectangle = scene.addRect(
                start,
                30,
                max(end - start, 2),
                52,
                QPen(Qt.PenStyle.NoPen),
                color,
            )
            rectangle.setToolTip(
                f"{item_label} {index + 1}: {item.clip_id} "
                f"({format_ticks(int(item.logical_start_90k))} - "
                f"{format_ticks(int(item.logical_end_90k))})"
            )
            label = scene.addText(f"{index + 1}  {item.clip_id}")
            label.setDefaultTextColor(QColor("#ffffff"))
            label.setPos(start + 4, 43)
        chapter_pen = QPen(QColor("#d14545"), 2)
        for mark in playlist.marks:
            if mark.time_90k is None:
                continue
            x = int(mark.time_90k) * width / total
            line = scene.addLine(x, 18, x, 94, chapter_pen)
            line.setToolTip(
                f"{chapter_label} {mark.index + 1}: {format_ticks(int(mark.time_90k))}"
            )
        scene.addLine(0, 104, width, 104, QPen(self.palette().text().color()))
        scene.addText("00:00:00.000").setPos(0, 105)
        end_label = scene.addText(format_ticks(total))
        end_label.setPos(max(width - 90, 0), 105)
        scene.setSceneRect(QRectF(0, 0, width, 140))
        self._render_user_boundaries()
        self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    @property
    def user_boundaries(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self._user_boundaries.items(), key=lambda item: (item[1], item[0])))

    def set_user_boundaries(self, boundaries: tuple[tuple[str, int], ...]) -> None:
        self._user_boundaries = dict(boundaries)
        self._render_user_boundaries()

    def add_user_boundary(self, time_90k: int, boundary_id: str | None = None) -> str:
        identifier = boundary_id or self._next_boundary_id()
        self._user_boundaries[identifier] = self._clamp_ticks(time_90k)
        self._render_user_boundaries()
        self.user_boundary_added.emit(identifier, self._user_boundaries[identifier])
        return identifier

    def remove_user_boundary(self, boundary_id: str) -> None:
        if boundary_id in self._user_boundaries:
            del self._user_boundaries[boundary_id]
            self._render_user_boundaries()
            self.user_boundary_deleted.emit(boundary_id)

    def _render_user_boundaries(self) -> None:
        scene = self.scene()
        for item in self._boundary_items.values():
            scene.removeItem(item)
        self._boundary_items.clear()
        if self._playlist is None or int(self._playlist.duration_90k) <= 0:
            return
        total = int(self._playlist.duration_90k)
        for boundary_id, time_90k in self.user_boundaries:
            x = time_90k * self._timeline_width / total
            item = scene.addLine(0, 12, 0, 100, QPen(QColor("#f1a12b"), 3))
            item.setPos(x, 0)
            item.setData(0, boundary_id)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            item.setToolTip(f"{boundary_id}: {format_ticks(time_90k)}")
            self._boundary_items[boundary_id] = item

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

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._playlist is None:
            return
        total = int(self._playlist.duration_90k)
        for boundary_id, item in self._boundary_items.items():
            if not item.isSelected():
                continue
            x = max(0.0, min(item.pos().x(), self._timeline_width))
            item.setPos(x, 0)
            time_90k = self._clamp_ticks(int(x * total / self._timeline_width))
            self._user_boundaries[boundary_id] = time_90k
            item.setToolTip(f"{boundary_id}: {format_ticks(time_90k)}")
            self.user_boundary_moved.emit(boundary_id, time_90k)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete:
            selected_ids = tuple(
                str(item.data(0)) for item in self.scene().selectedItems() if item.data(0)
            )
            for boundary_id in selected_ids:
                self.remove_user_boundary(boundary_id)
            event.accept()
            return
        super().keyPressEvent(event)

    def _clamp_ticks(self, ticks: int) -> int:
        maximum = int(self._playlist.duration_90k) if self._playlist is not None else ticks
        return max(0, min(ticks, maximum))

    def _next_boundary_id(self) -> str:
        index = 1
        while f"user:{index}" in self._user_boundaries:
            index += 1
        return f"user:{index}"

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)


def format_ticks(ticks: int) -> str:
    milliseconds = ticks // 90
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
