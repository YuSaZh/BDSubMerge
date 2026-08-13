"""Modal source-recovery view for a pending project snapshot."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bdsubmerge.project import RestoredProject, SourceCheck, SourceState

TranslationLookup = Callable[..., str]
RelocationHandler = Callable[[SourceCheck], RestoredProject | None]


class ProjectRelocationDialog(QDialog):
    """Keep unresolved sources visible while the user relocates them one by one."""

    def __init__(
        self,
        restored: RestoredProject,
        *,
        tr: TranslationLookup,
        relocate: RelocationHandler,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tr = tr
        self._relocate = relocate
        self._restored = restored
        self.setWindowTitle(tr("project.relocation.title"))
        self.setModal(True)
        self.resize(820, 420)

        layout = QVBoxLayout(self)
        summary = QLabel(tr("project.relocation.summary"))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.sources = QTableWidget(0, 3)
        self.sources.setHorizontalHeaderLabels(
            (
                tr("project.relocation.source"),
                tr("project.relocation.state"),
                tr("project.relocation.path"),
            )
        )
        self.sources.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sources.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.sources.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sources.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.sources)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.locate_button = QPushButton(tr("project.relocation.locate"))
        self.continue_button = QPushButton(tr("project.relocation.continue"))
        self.buttons.addButton(
            self.locate_button,
            QDialogButtonBox.ButtonRole.ActionRole,
        )
        self.buttons.addButton(
            self.continue_button,
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText(tr("common.cancel"))
        self.locate_button.clicked.connect(self._locate_selected)
        self.continue_button.clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.set_restored(restored)

    @property
    def restored(self) -> RestoredProject:
        return self._restored

    def set_restored(self, restored: RestoredProject) -> None:
        self._restored = restored
        unresolved = tuple(
            check
            for check in restored.source_checks
            if check.state is not SourceState.UNCHANGED
        )
        self.sources.setRowCount(0)
        for check in unresolved:
            row = self.sources.rowCount()
            self.sources.insertRow(row)
            source_item = QTableWidgetItem(check.id)
            source_item.setData(Qt.ItemDataRole.UserRole, check.id)
            state_item = QTableWidgetItem(
                self._tr(
                    "project.missing"
                    if check.state is SourceState.MISSING
                    else "project.changed"
                )
            )
            path_item = QTableWidgetItem(str(check.path))
            self.sources.setItem(row, 0, source_item)
            self.sources.setItem(row, 1, state_item)
            self.sources.setItem(row, 2, path_item)
        if unresolved:
            self.sources.selectRow(0)
        self.locate_button.setEnabled(bool(unresolved))
        self.continue_button.setEnabled(not unresolved)

    def _locate_selected(self) -> None:
        row = self.sources.currentRow()
        item = self.sources.item(row, 0) if row >= 0 else None
        source_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        check = next(
            (
                candidate
                for candidate in self._restored.source_checks
                if candidate.id == source_id
            ),
            None,
        )
        updated = self._relocate(check) if check is not None else None
        if updated is not None:
            self.set_restored(updated)
