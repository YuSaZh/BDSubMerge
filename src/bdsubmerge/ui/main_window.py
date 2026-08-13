"""Single-window workspace driven exclusively by application services."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast, override

from PySide6.QtCore import QByteArray, QPoint, QSettings, Qt, QThreadPool, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from bdsubmerge.application import (
    ApplicationIssue,
    BdmvApplicationService,
    ExecuteMergeRequest,
    ExecuteMergeResult,
    LoadSubtitlesRequest,
    LoadSubtitlesResult,
    MergeApplicationService,
    PlaylistSelectionRequest,
    PlaylistSelectionResult,
    PreparedMerge,
    PrepareMergeRequest,
    ScanRequest,
    ScanResult,
    SubtitleApplicationService,
    SubtitleInput,
    build_playlist_boundaries,
    select_playlists,
)
from bdsubmerge.domain.models import PlaylistInfo
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.mapping import (
    BoundaryKind,
    BoundarySource,
    MappingLock,
    TimelineBoundary,
    boundary,
)
from bdsubmerge.output import (
    CollisionPolicy,
    DiscNameOutputTarget,
    FullPathOutputTarget,
    JRiverOutputTarget,
    OutputContext,
    OutputTarget,
    PlaylistOutputTarget,
    TemplateOutputTarget,
)
from bdsubmerge.project import (
    BoundarySnapshot,
    ConflictPolicySnapshot,
    MappingSnapshot,
    OutputState,
    ProjectSchemaError,
    ProjectState,
    RestoredProject,
    SourceState,
    SubtitleState,
)

from .project_io import capture_and_save, load_restored_project, qt_atomic_project_writer
from .tasks import CancellationToken, ServiceTask
from .theme import ThemeMode, apply_theme
from .timeline import TimelineView, format_ticks
from .translations import TranslationCatalog

SUPPORTED_SUBTITLES = frozenset({".ass", ".ssa", ".srt", ".sup"})


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        bdmv_service: BdmvApplicationService | None = None,
        subtitle_service: SubtitleApplicationService | None = None,
        merge_service: MergeApplicationService | None = None,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__()
        self.bdmv_service = bdmv_service or BdmvApplicationService()
        self.subtitle_service = subtitle_service or SubtitleApplicationService()
        self.merge_service = merge_service or MergeApplicationService()
        self.settings = settings or QSettings()
        locale = str(self.settings.value("ui/language", "zh_CN"))
        self.translations = TranslationCatalog(locale)
        self.thread_pool = QThreadPool.globalInstance()
        self.active_task: ServiceTask[object] | None = None
        self.cancellation: CancellationToken | None = None
        self.scan_result: ScanResult | None = None
        self.selected_playlists: tuple[PlaylistInfo, ...] = ()
        self.selected_playlist: PlaylistInfo | None = None
        self.playlist_selection: PlaylistSelectionResult | None = None
        self.primary_playlist_stem: str | None = None
        self.subtitle_result: LoadSubtitlesResult | None = None
        self.prepared: PreparedMerge | None = None
        self.mapping_dirty = False
        self.project_path: Path | None = None
        self.restored_mapping_locks: tuple[MappingLock, ...] = ()
        self.restored_mapping_snapshots: tuple[MappingSnapshot, ...] = ()
        self.pending_project: RestoredProject | None = None
        self.pending_restore_after_scan = False
        self.subtitle_paths: list[Path] = []
        self.locked_subtitles: set[Path] = set()
        self.subtitle_offsets_ms: dict[Path, int] = {}
        self.error_details: list[str] = []

        self.setAcceptDrops(True)
        self.setMinimumSize(980, 700)
        self._build_ui()
        self._restore_settings()
        self.retranslate_ui()
        self._connect_signals()
        self._update_actions()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(8)

        path_layout = QHBoxLayout()
        self.path_label = QLabel()
        self.path_edit = QLineEdit()
        self.path_edit.setClearButtonEnabled(True)
        self.choose_path_button = QPushButton()
        self.scan_button = QPushButton()
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(self.choose_path_button)
        path_layout.addWidget(self.scan_button)
        root.addLayout(path_layout)

        upper = QSplitter(Qt.Orientation.Horizontal)
        playlist_widget = QWidget()
        playlist_layout = QVBoxLayout(playlist_widget)
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        self.playlist_title = QLabel()
        self.playlist_title.setProperty("sectionHeading", True)
        self.playlist_search = QLineEdit()
        self.playlist_search.setClearButtonEnabled(True)
        self.primary_playlist_row = QWidget()
        primary_playlist_layout = QHBoxLayout(self.primary_playlist_row)
        primary_playlist_layout.setContentsMargins(0, 0, 0, 0)
        self.primary_playlist_label = QLabel()
        self.primary_playlist_combo = QComboBox()
        primary_playlist_layout.addWidget(self.primary_playlist_label)
        primary_playlist_layout.addWidget(self.primary_playlist_combo, 1)
        self.playlist_compatibility = QLabel()
        self.playlist_compatibility.setWordWrap(True)
        self.playlist_warning = QLabel()
        self.playlist_warning.setWordWrap(True)
        self.playlist_warning.setProperty("severity", "warning")
        self.playlist_table = QTableWidget(0, 6)
        self.playlist_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.playlist_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.playlist_table.setSortingEnabled(True)
        self.playlist_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.playlist_table.horizontalHeader().setStretchLastSection(True)
        playlist_layout.addWidget(self.playlist_title)
        playlist_layout.addWidget(self.playlist_search)
        playlist_layout.addWidget(self.primary_playlist_row)
        playlist_layout.addWidget(self.playlist_compatibility)
        playlist_layout.addWidget(self.playlist_warning)
        playlist_layout.addWidget(self.playlist_table)
        self.primary_playlist_row.setVisible(False)
        self.playlist_compatibility.setVisible(False)
        self.playlist_warning.setVisible(False)

        timeline_widget = QWidget()
        timeline_layout = QVBoxLayout(timeline_widget)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_title = QLabel()
        self.timeline = TimelineView()
        self.timeline.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        timeline_layout.addWidget(self.timeline_title)
        timeline_layout.addWidget(self.timeline)
        upper.addWidget(playlist_widget)
        upper.addWidget(timeline_widget)
        upper.setSizes([430, 650])
        root.addWidget(upper, 2)

        self.subtitle_group = QGroupBox()
        subtitle_layout = QVBoxLayout(self.subtitle_group)
        subtitle_toolbar = QHBoxLayout()
        self.add_subtitle_button = QPushButton()
        self.remove_subtitle_button = QPushButton()
        self.offset_button = QPushButton()
        self.lock_button = QPushButton()
        subtitle_toolbar.addWidget(self.add_subtitle_button)
        subtitle_toolbar.addWidget(self.remove_subtitle_button)
        subtitle_toolbar.addWidget(self.offset_button)
        subtitle_toolbar.addWidget(self.lock_button)
        subtitle_toolbar.addStretch()
        self.mapping_table = QTableWidget(0, 11)
        self.mapping_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mapping_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.mapping_table.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self.mapping_table.setDragEnabled(True)
        self.mapping_table.setAcceptDrops(True)
        self.mapping_table.setDropIndicatorShown(True)
        self.mapping_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.mapping_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        subtitle_layout.addLayout(subtitle_toolbar)
        subtitle_layout.addWidget(self.mapping_table)
        root.addWidget(self.subtitle_group, 2)

        self.output_group = QGroupBox()
        output_layout = QHBoxLayout(self.output_group)
        output_form = QFormLayout()
        self.output_mode = QComboBox()
        self.output_directory = QLineEdit()
        self.output_directory.setClearButtonEnabled(True)
        self.output_directory_browse = QPushButton()
        self.output_directory_row = QWidget()
        directory_layout = QHBoxLayout(self.output_directory_row)
        directory_layout.setContentsMargins(0, 0, 0, 0)
        directory_layout.addWidget(self.output_directory, 1)
        directory_layout.addWidget(self.output_directory_browse)
        self.output_template = QLineEdit("{disc_name}_{playlist_stem}.{format}")
        self.output_path = QLineEdit()
        self.output_path.setClearButtonEnabled(True)
        self.output_browse = QPushButton()
        path_row = QHBoxLayout()
        path_row.addWidget(self.output_path, 1)
        path_row.addWidget(self.output_browse)
        self.output_encoding = QComboBox()
        self.output_encoding.addItems(["utf-8-sig", "utf-8"])
        self.collision_policy = QComboBox()
        self.output_mode_label = QLabel()
        self.output_directory_label = QLabel()
        self.output_template_label = QLabel()
        self.output_path_label = QLabel()
        self.output_encoding_label = QLabel()
        self.collision_label = QLabel()
        output_form.addRow(self.output_mode_label, self.output_mode)
        output_form.addRow(self.output_directory_label, self.output_directory_row)
        output_form.addRow(self.output_template_label, self.output_template)
        output_form.addRow(self.output_path_label, path_row)
        output_form.addRow(self.output_encoding_label, self.output_encoding)
        output_form.addRow(self.collision_label, self.collision_policy)
        output_layout.addLayout(output_form, 3)
        preflight_column = QVBoxLayout()
        self.preflight_title = QLabel()
        self.preflight_summary = QPlainTextEdit()
        self.preflight_summary.setReadOnly(True)
        self.preflight_summary.setMaximumBlockCount(200)
        preflight_column.addWidget(self.preflight_title)
        preflight_column.addWidget(self.preflight_summary)
        output_layout.addLayout(preflight_column, 2)
        root.addWidget(self.output_group)

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_panel = QWidget()
        advanced_layout = QHBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(20, 0, 0, 0)
        self.accept_low_confidence = QCheckBox()
        self.offset_label = QLabel()
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-3_600_000, 3_600_000)
        self.offset_spin.setSuffix(" ms")
        advanced_layout.addWidget(self.accept_low_confidence)
        advanced_layout.addWidget(self.offset_label)
        advanced_layout.addWidget(self.offset_spin)
        self.project_notes_label = QLabel()
        self.project_notes = QLineEdit()
        advanced_layout.addWidget(self.project_notes_label)
        advanced_layout.addWidget(self.project_notes, 1)
        advanced_layout.addStretch()
        self.advanced_panel.setVisible(False)
        root.addWidget(self.advanced_toggle)
        root.addWidget(self.advanced_panel)

        actions = QHBoxLayout()
        self.open_button = QPushButton()
        self.save_button = QPushButton()
        self.auto_map_button = QPushButton()
        self.preflight_button = QPushButton()
        self.generate_button = QPushButton()
        actions.addWidget(self.open_button)
        actions.addWidget(self.save_button)
        actions.addStretch()
        actions.addWidget(self.auto_map_button)
        actions.addWidget(self.preflight_button)
        actions.addWidget(self.generate_button)
        root.addLayout(actions)

        task_row = QHBoxLayout()
        self.task_status = QLabel()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.cancel_button = QPushButton()
        self.cancel_button.setEnabled(False)
        self.details_button = QPushButton()
        self.details_button.setCheckable(True)
        task_row.addWidget(self.task_status)
        task_row.addWidget(self.progress, 1)
        task_row.addWidget(self.cancel_button)
        task_row.addWidget(self.details_button)
        root.addLayout(task_row)
        self.error_panel = QPlainTextEdit()
        self.error_panel.setReadOnly(True)
        self.error_panel.setVisible(False)
        self.error_panel.setMaximumHeight(150)
        root.addWidget(self.error_panel)

        self.setCentralWidget(central)
        self._build_settings_menu()

    def _build_settings_menu(self) -> None:
        self.settings_menu = QMenu(self)
        self.language_menu = self.settings_menu.addMenu("")
        self.language_zh = QAction(self)
        self.language_en = QAction(self)
        self.language_zh.setCheckable(True)
        self.language_en.setCheckable(True)
        self.language_menu.addActions((self.language_zh, self.language_en))
        self.theme_menu = self.settings_menu.addMenu("")
        self.theme_system = QAction(self)
        self.theme_light = QAction(self)
        self.theme_dark = QAction(self)
        for action in (self.theme_system, self.theme_light, self.theme_dark):
            action.setCheckable(True)
            self.theme_menu.addAction(action)
        self.menuBar().addMenu(self.settings_menu)
        self.playlist_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def _connect_signals(self) -> None:
        self.choose_path_button.clicked.connect(self.choose_bdmv)
        self.open_button.clicked.connect(self.open_project)
        self.save_button.clicked.connect(self.save_project)
        self.scan_button.clicked.connect(self.start_scan)
        self.path_edit.returnPressed.connect(self.start_scan)
        self.playlist_search.textChanged.connect(self.filter_playlists)
        self.playlist_table.itemSelectionChanged.connect(self.select_playlist)
        self.primary_playlist_combo.currentIndexChanged.connect(
            self.select_primary_playlist
        )
        self.add_subtitle_button.clicked.connect(self.choose_subtitles)
        self.remove_subtitle_button.clicked.connect(self.remove_subtitles)
        self.offset_button.clicked.connect(self.apply_batch_offset)
        self.lock_button.clicked.connect(self.toggle_rows_locked)
        self.output_mode.currentIndexChanged.connect(self.output_mode_changed)
        self.output_browse.clicked.connect(self.choose_output)
        self.output_directory_browse.clicked.connect(self.choose_output_directory)
        self.collision_policy.currentIndexChanged.connect(self._invalidate_preflight)
        self.output_encoding.currentIndexChanged.connect(self._invalidate_preflight)
        self.output_path.textChanged.connect(self._invalidate_preflight)
        self.output_directory.textChanged.connect(self.output_configuration_changed)
        self.output_template.textChanged.connect(self.output_configuration_changed)
        self.accept_low_confidence.toggled.connect(self._invalidate_preflight)
        self.auto_map_button.clicked.connect(self.start_preflight)
        self.preflight_button.clicked.connect(self.start_preflight)
        self.generate_button.clicked.connect(self.start_generate)
        self.cancel_button.clicked.connect(self.cancel_active_task)
        self.details_button.toggled.connect(self.error_panel.setVisible)
        self.advanced_toggle.toggled.connect(self.toggle_advanced)
        self.timeline.user_boundary_added.connect(self._user_boundary_changed)
        self.timeline.user_boundary_moved.connect(self._user_boundary_changed)
        self.timeline.user_boundary_deleted.connect(self._user_boundary_deleted)
        self.playlist_table.customContextMenuRequested.connect(self.show_playlist_context_menu)
        self.language_zh.triggered.connect(lambda: self.set_language("zh_CN"))
        self.language_en.triggered.connect(lambda: self.set_language("en_US"))
        self.theme_system.triggered.connect(lambda: self.set_theme(ThemeMode.SYSTEM))
        self.theme_light.triggered.connect(lambda: self.set_theme(ThemeMode.LIGHT))
        self.theme_dark.triggered.connect(lambda: self.set_theme(ThemeMode.DARK))

    def retranslate_ui(self) -> None:
        tr = self.translations.text
        self.setWindowTitle(tr("app.title"))
        self.path_label.setText(tr("path.label"))
        self.choose_path_button.setText(tr("path.choose"))
        self.scan_button.setText(tr("path.scan"))
        self.playlist_title.setText(tr("playlist.title"))
        self.playlist_search.setPlaceholderText(tr("playlist.search"))
        self.primary_playlist_label.setText(tr("playlist.primary"))
        self.playlist_table.setHorizontalHeaderLabels(
            [
                tr("playlist.name"),
                tr("playlist.duration"),
                tr("playlist.items"),
                tr("playlist.chapters"),
                tr("playlist.score"),
                tr("playlist.confidence"),
            ]
        )
        self.timeline_title.setText(tr("timeline.title"))
        self.subtitle_group.setTitle(tr("subtitles.title"))
        self.add_subtitle_button.setText(tr("subtitles.add"))
        self.remove_subtitle_button.setText(tr("subtitles.remove"))
        self.offset_button.setText(tr("subtitles.offset"))
        self.lock_button.setText(tr("subtitles.lock"))
        self.mapping_table.setHorizontalHeaderLabels(
            [
                tr("mapping.index"),
                tr("mapping.file"),
                tr("mapping.format"),
                tr("mapping.duration"),
                tr("mapping.start"),
                tr("mapping.end"),
                tr("mapping.interval"),
                tr("mapping.offset"),
                tr("mapping.confidence"),
                tr("mapping.status"),
                tr("mapping.warning"),
            ]
        )
        self.output_group.setTitle(tr("output.title"))
        self.output_mode_label.setText(tr("output.mode"))
        self.output_directory_label.setText(tr("output.directory"))
        self.output_template_label.setText(tr("output.template"))
        self.output_path_label.setText(tr("output.path"))
        self.output_encoding_label.setText(tr("output.encoding"))
        self.collision_label.setText(tr("output.collision"))
        self.output_browse.setText(tr("common.browse"))
        self.output_directory_browse.setText(tr("common.browse"))
        self._reset_combo(
            self.output_mode,
            (
                (tr("output.jriver"), "jriver"),
                (tr("output.playlist"), "playlist"),
                (tr("output.disc"), "disc_name"),
                (tr("output.custom"), "custom"),
                (tr("output.full"), "full_path"),
            ),
        )
        self._reset_combo(
            self.collision_policy,
            (
                (tr("collision.abort"), CollisionPolicy.ABORT.value),
                (tr("collision.overwrite"), CollisionPolicy.OVERWRITE.value),
                (tr("collision.backup"), CollisionPolicy.BACKUP.value),
                (tr("collision.rename"), CollisionPolicy.AUTO_RENAME.value),
            ),
        )
        self.preflight_title.setText(tr("preflight.title"))
        if not self.preflight_summary.toPlainText():
            self.preflight_summary.setPlainText(tr("preflight.waiting"))
        self.save_button.setText(tr("actions.save"))
        self.open_button.setText(tr("actions.open"))
        self.auto_map_button.setText(tr("actions.map"))
        self.preflight_button.setText(tr("actions.preflight"))
        self.generate_button.setText(tr("actions.generate"))
        self.cancel_button.setText(tr("task.cancel"))
        self.details_button.setText(tr("details.show"))
        self.advanced_toggle.setText(tr("advanced.title"))
        self.accept_low_confidence.setText(tr("advanced.low_confidence"))
        self.offset_label.setText(tr("advanced.offset"))
        self.project_notes_label.setText(tr("project.notes"))
        self.settings_menu.setTitle(tr("settings.menu"))
        self.language_menu.setTitle(tr("settings.language"))
        self.theme_menu.setTitle(tr("settings.theme"))
        self.language_zh.setText(tr("language.zh"))
        self.language_en.setText(tr("language.en"))
        self.theme_system.setText(tr("theme.system"))
        self.theme_light.setText(tr("theme.light"))
        self.theme_dark.setText(tr("theme.dark"))
        self.language_zh.setChecked(self.translations.locale == "zh_CN")
        self.language_en.setChecked(self.translations.locale == "en_US")
        restored_mode = self.output_mode.property("restoredMode")
        if restored_mode:
            restored_index = self.output_mode.findData(str(restored_mode))
            if restored_index >= 0:
                self.output_mode.setCurrentIndex(restored_index)
            self.output_mode.setProperty("restoredMode", None)
        if self.active_task is None:
            self.task_status.setText(tr("task.idle"))
        self._refresh_playlist_selection()
        self._update_output_controls()
        self._show_timeline()

    @staticmethod
    def _reset_combo(combo: QComboBox, entries: tuple[tuple[str, str], ...]) -> None:
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for label, value in entries:
            combo.addItem(label, value)
        index = combo.findData(previous)
        combo.setCurrentIndex(max(index, 0))
        combo.blockSignals(False)

    @Slot()
    def choose_bdmv(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self.translations.text("dialog.select_bdmv"),
            self.path_edit.text() or str(self.settings.value("recent/bdmv", "")),
        )
        if selected:
            self.path_edit.setText(selected)
            self.start_scan()

    @Slot()
    def start_scan(self) -> None:
        path = self.path_edit.text().strip()
        if not path or self.active_task is not None:
            return
        request = ScanRequest(Path(path))
        self._start_task(
            lambda: self.bdmv_service.scan(request),
            self.translations.text("task.scanning"),
            self._scan_finished,
        )

    def _scan_finished(self, value: object) -> None:
        result = cast(ScanResult, value)
        self.scan_result = result
        self.selected_playlists = ()
        self.selected_playlist = None
        self.playlist_selection = None
        self.primary_playlist_stem = None
        self.playlist_table.setSortingEnabled(False)
        self.playlist_table.setRowCount(0)
        for playlist in result.playlists:
            row = self.playlist_table.rowCount()
            self.playlist_table.insertRow(row)
            values = (
                playlist.stem,
                format_ticks(int(playlist.duration_90k)),
                str(len(playlist.play_items)),
                str(len(playlist.marks)),
                str(playlist.score),
                playlist.confidence.value,
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column in {2, 3, 4}:
                    item.setData(Qt.ItemDataRole.DisplayRole, int(text))
                self.playlist_table.setItem(row, column, item)
        self.playlist_table.setSortingEnabled(True)
        self._record_issues(result.issues)
        selected_stem = (
            self.pending_project.state.playlist_stem
            if self.pending_project is not None
            else result.playlists[0].stem if result.playlists else ""
        )
        for row in range(self.playlist_table.rowCount()):
            selected_item = self.playlist_table.item(row, 0)
            if selected_item is not None and selected_item.text() == selected_stem:
                self.playlist_table.selectRow(row)
                break
        self.settings.setValue("recent/bdmv", self.path_edit.text())
        self.statusBar().showMessage(
            self.translations.text("status.scan_complete", count=len(result.playlists)), 6000
        )
        self._update_actions()
        if self.pending_project is not None:
            self.pending_restore_after_scan = True

    @Slot()
    def select_playlist(self) -> None:
        if self.scan_result is None:
            return
        selected_stems = tuple(
            sorted(
                str(index.data())
                for index in self.playlist_table.selectionModel().selectedRows(0)
            )
        )
        previous_stems = tuple(sorted(item.stem for item in self.selected_playlists))
        if selected_stems != previous_stems:
            self.primary_playlist_stem = None
        by_stem = {playlist.stem: playlist for playlist in self.scan_result.playlists}
        self.selected_playlists = tuple(
            by_stem[stem] for stem in selected_stems if stem in by_stem
        )
        self._refresh_playlist_selection()
        self._invalidate_preflight()
        self._show_timeline()
        self.refresh_output_path()
        self._update_actions()

    @Slot()
    def select_primary_playlist(self) -> None:
        value = self.primary_playlist_combo.currentData()
        self.primary_playlist_stem = str(value) if value else None
        self._refresh_playlist_selection(rebuild_primary=False)
        self._invalidate_preflight()
        self._show_timeline()
        self.refresh_output_path()

    @Slot()
    def output_mode_changed(self) -> None:
        self._refresh_playlist_selection()
        self._update_output_controls()
        self._invalidate_preflight()
        self._show_timeline()
        self.refresh_output_path()

    @Slot()
    def output_configuration_changed(self) -> None:
        self._invalidate_preflight()
        self.refresh_output_path()

    def _update_output_controls(self) -> None:
        mode = str(self.output_mode.currentData() or "jriver")
        has_directory = mode in {"disc_name", "custom"}
        has_template = mode == "custom"
        self.output_directory_label.setVisible(has_directory)
        self.output_directory_row.setVisible(has_directory)
        self.output_template_label.setVisible(has_template)
        self.output_template.setVisible(has_template)
        self.output_path.setReadOnly(mode != "full_path")
        self.output_browse.setEnabled(mode == "full_path")

    def _refresh_playlist_selection(self, *, rebuild_primary: bool = True) -> None:
        if not self.selected_playlists:
            self.playlist_selection = None
            self.selected_playlist = None
            self.primary_playlist_row.setVisible(False)
            self.playlist_compatibility.setVisible(False)
            self.playlist_warning.setVisible(False)
            return
        uses_jriver = str(self.output_mode.currentData() or "jriver") == "jriver"
        result = select_playlists(
            PlaylistSelectionRequest(
                self.selected_playlists,
                jriver_enabled=uses_jriver,
                primary_stem=self.primary_playlist_stem if uses_jriver else None,
            )
        )
        requires_primary = uses_jriver and len(result.equivalence_groups) > 1
        if rebuild_primary:
            self.primary_playlist_combo.blockSignals(True)
            self.primary_playlist_combo.clear()
            self.primary_playlist_combo.addItem(
                self.translations.text("playlist.primary_choose"), None
            )
            for playlist in result.selected_playlists:
                self.primary_playlist_combo.addItem(playlist.stem, playlist.stem)
            selected_index = self.primary_playlist_combo.findData(
                self.primary_playlist_stem
            )
            self.primary_playlist_combo.setCurrentIndex(max(selected_index, 0))
            self.primary_playlist_combo.blockSignals(False)
        self.primary_playlist_row.setVisible(requires_primary)
        warning_messages = tuple(
            issue.message
            for issue in result.issues
            if issue.code == "non_equivalent_jriver_timelines"
        )
        if any(issue.code == "jriver_primary_required" for issue in result.issues):
            warning_messages = (
                *warning_messages,
                self.translations.text("playlist.primary_required"),
            )
        self.playlist_warning.setText("\n".join(warning_messages))
        self.playlist_warning.setVisible(bool(warning_messages))
        if result.compatible_stems:
            self.playlist_compatibility.setText(
                self.translations.text(
                    "playlist.compatible",
                    stems=", ".join(result.compatible_stems),
                )
            )
            self.playlist_compatibility.setVisible(True)
        else:
            self.playlist_compatibility.setVisible(False)
        self.playlist_selection = result
        if result.ready and uses_jriver:
            self.selected_playlist = result.primary_playlist
        elif result.ready:
            current_row = self.playlist_table.currentRow()
            current_item = (
                self.playlist_table.item(current_row, 0) if current_row >= 0 else None
            )
            current_stem = current_item.text() if current_item is not None else ""
            self.selected_playlist = next(
                (
                    playlist
                    for playlist in result.selected_playlists
                    if playlist.stem == current_stem
                ),
                result.selected_playlists[0],
            )
        else:
            self.selected_playlist = None

    @Slot()
    def save_project(self) -> None:
        if (
            self.selected_playlist is None
            or self.scan_result is None
            or self.scan_result.layout is None
        ):
            self.statusBar().showMessage(self.translations.text("status.no_playlist"), 5000)
            return
        if self.subtitle_result is None or not self.subtitle_result.ready:
            self.statusBar().showMessage(self.translations.text("status.no_subtitles"), 5000)
            return
        self._sync_subtitle_order()
        selected = str(self.project_path or self.settings.value("recent/project", ""))
        if self.project_path is None:
            chosen, _ = QFileDialog.getSaveFileName(
                self,
                self.translations.text("dialog.save_project"),
                selected,
                "BDSubMerge (*.bdsm.json)",
            )
            if not chosen:
                return
            self.project_path = Path(chosen)
        try:
            state = self._project_state()
            capture_and_save(state, self.project_path)
        except (OSError, ProjectSchemaError, ValueError) as error:
            self._record_error(str(error))
            return
        self.settings.setValue("recent/project", str(self.project_path))
        self.statusBar().showMessage(self.translations.text("status.project_saved"), 6000)

    @Slot()
    def open_project(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            self.translations.text("dialog.open_project"),
            str(self.settings.value("recent/project", "")),
            "BDSubMerge (*.bdsm.json)",
        )
        if not chosen:
            return
        project_path = Path(chosen)
        try:
            _, restored = load_restored_project(project_path)
        except (OSError, ProjectSchemaError, ValueError) as error:
            self._record_error(str(error))
            return
        self.project_path = project_path
        self.pending_project = restored
        self.settings.setValue("recent/project", str(project_path))
        self._show_source_checks(restored)
        self.path_edit.setText(str(restored.state.bdmv_path))
        self.start_scan()

    def _project_state(self) -> ProjectState:
        assert self.scan_result is not None and self.scan_result.layout is not None
        assert self.selected_playlist is not None and self.subtitle_result is not None
        boundaries = self._project_boundaries()
        mappings = self._project_mappings()
        output = self._project_output_state()
        subtitles = tuple(
            SubtitleState(
                id=f"episode-{index + 1}",
                path=asset.path,
                format=asset.format.value,
                encoding=asset.encoding or "binary",
                order=index,
                raw_end_90k=asset.analysis.raw_end_ticks,
                effective_end_90k=asset.analysis.effective_end_ticks,
                event_count=asset.analysis.event_count,
                style_count=asset.analysis.style_count,
                warnings=("duration estimated",) if asset.analysis.duration_estimated else (),
            )
            for index, asset in enumerate(self.subtitle_result.assets)
        )
        return ProjectState(
            bdmv_path=self.scan_result.layout.bdmv_path,
            index_bdmv_path=self.scan_result.layout.index_bdmv_path,
            playlist_path=self.selected_playlist.path,
            playlist_stem=self.selected_playlist.stem,
            playlist_duration_90k=int(self.selected_playlist.duration_90k),
            playlist_timeline_fingerprint=self.selected_playlist.timeline_fingerprint,
            subtitles=subtitles,
            boundaries=boundaries,
            mappings=mappings,
            outputs=(output,),
            conflict_policy=ConflictPolicySnapshot(),
            ui_notes=self.project_notes.text(),
        )

    def _project_boundaries(self) -> tuple[BoundarySnapshot, ...]:
        assert self.selected_playlist is not None
        automatic = build_playlist_boundaries(self.selected_playlist)
        snapshots = [
            BoundarySnapshot(
                item.id,
                int(item.time_90k),
                tuple(sorted(kind.value for kind in item.kinds)),
                tuple(source.reference for source in item.sources),
                item.confidence,
                item.enabled,
                item.user_created,
                item.note,
            )
            for item in automatic
        ]
        snapshots.extend(
            BoundarySnapshot(
                boundary_id,
                time_90k,
                ("user",),
                ("ui",),
                100,
                True,
                True,
            )
            for boundary_id, time_90k in self.timeline.user_boundaries
        )
        return tuple(snapshots)

    def _project_mappings(self) -> tuple[MappingSnapshot, ...]:
        if self.prepared is None or self.prepared.mapping is None:
            return self.restored_mapping_snapshots
        return tuple(
            MappingSnapshot(
                mapping.episode_id,
                mapping.start_boundary.id,
                mapping.end_boundary.id,
                int(mapping.start_boundary.time_90k),
                int(mapping.end_boundary.time_90k),
                int(mapping.manual_offset_90k),
                mapping.locked or Path(mapping.subtitle_ref) in self.locked_subtitles,
                mapping.confidence.value,
                mapping.warnings,
            )
            for mapping in self.prepared.mapping.mappings
        )

    def _project_output_state(self) -> OutputState:
        preset = str(self.output_mode.currentData() or "jriver")
        collision = str(self.collision_policy.currentData() or CollisionPolicy.ABORT.value)
        resolved = Path(self.output_path.text()) if self.output_path.text().strip() else None
        template = self.output_template.text().strip() if preset == "custom" else ""
        return OutputState(
            "primary",
            preset,
            template,
            resolved,
            self.output_encoding.currentText(),
            collision,
            "backup" if collision == CollisionPolicy.BACKUP.value else "none",
        )

    def _continue_project_restore(self) -> None:
        assert self.pending_project is not None
        if self.selected_playlist is None:
            self.pending_project = None
            self.statusBar().showMessage(
                self.translations.text("status.project_incomplete"), 8000
            )
            return
        state = self.pending_project.state
        self.project_notes.setText(state.ui_notes)
        if state.outputs:
            output = state.outputs[0]
            mode_index = self.output_mode.findData(output.preset)
            if mode_index >= 0:
                self.output_mode.setCurrentIndex(mode_index)
            policy_index = self.collision_policy.findData(output.collision_policy)
            if policy_index >= 0:
                self.collision_policy.setCurrentIndex(policy_index)
            encoding_index = self.output_encoding.findText(output.encoding)
            if encoding_index >= 0:
                self.output_encoding.setCurrentIndex(encoding_index)
            if output.resolved_path is not None:
                if output.preset in {"disc_name", "custom"}:
                    self.output_directory.setText(str(output.resolved_path.parent))
                if output.preset == "custom" and output.path_template:
                    self.output_template.setText(output.path_template)
                self.output_path.setText(str(output.resolved_path))
        user_boundaries = tuple(
            (item.id, item.time_90k) for item in state.boundaries if item.user_created
        )
        self.timeline.set_user_boundaries(user_boundaries)
        existing_subtitles = tuple(item.path for item in state.subtitles if item.path.is_file())
        if existing_subtitles:
            request = LoadSubtitlesRequest(
                tuple(SubtitleInput(path) for path in existing_subtitles)
            )
            self._start_task(
                lambda: self.subtitle_service.load_ordered(request),
                self.translations.text("task.loading"),
                self._project_subtitles_finished,
            )
        else:
            self.pending_project = None
            self.statusBar().showMessage(
                self.translations.text("status.project_incomplete"), 8000
            )

    def _project_subtitles_finished(self, value: object) -> None:
        self._subtitles_finished(value)
        if self.pending_project is None:
            return
        state = self.pending_project.state
        by_id = {item.subtitle_id: item for item in state.mappings}
        self.restored_mapping_locks = tuple(
            MappingLock(
                item.subtitle_id,
                item.start_boundary_id,
                item.end_boundary_id,
                MediaTick90k(item.manual_offset_90k),
            )
            for item in state.mappings
            if item.locked
        )
        self.restored_mapping_snapshots = state.mappings
        subtitle_by_path = {item.path: item for item in state.subtitles}
        for row in range(self.mapping_table.rowCount()):
            row_path = self._row_path(row)
            subtitle = subtitle_by_path.get(row_path) if row_path is not None else None
            if subtitle is None:
                continue
            mapping = by_id.get(subtitle.id)
            if mapping is None:
                continue
            path = subtitle.path
            if mapping.locked:
                self.locked_subtitles.add(path)
            self.subtitle_offsets_ms[path] = mapping.manual_offset_90k // 90
            values = (
                mapping.start_boundary_id,
                mapping.end_boundary_id,
                format_ticks(mapping.end_90k - mapping.start_90k),
                f"{mapping.manual_offset_90k // 90} ms",
                mapping.confidence,
                self.translations.text("mapping.locked" if mapping.locked else "mapping.ready"),
                "; ".join(mapping.warnings),
            )
            for column, text in zip(range(4, 11), values, strict=True):
                cell = self.mapping_table.item(row, column)
                if cell is not None:
                    cell.setText(text)
        incomplete = self.pending_project.has_changed_sources
        self.pending_project = None
        status_key = "status.project_incomplete" if incomplete else "status.project_loaded"
        self.statusBar().showMessage(self.translations.text(status_key), 8000)

    def _show_source_checks(self, restored: RestoredProject) -> None:
        for check in restored.source_checks:
            if check.state is SourceState.UNCHANGED:
                continue
            key = "project.missing" if check.state is SourceState.MISSING else "project.changed"
            self._record_error(f"{self.translations.text(key)}: {check.id} - {check.path}")

    @Slot(QPoint)
    def show_playlist_context_menu(self, position: QPoint) -> None:
        if self.selected_playlist is None:
            return
        menu = QMenu(self)
        export_action = menu.addAction(self.translations.text("playlist.export"))
        selected = menu.exec(self.playlist_table.viewport().mapToGlobal(position))
        if selected is export_action:
            self.export_playlist_info()

    def export_playlist_info(self) -> None:
        if self.selected_playlist is None:
            return
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            self.translations.text("playlist.export_title"),
            f"{self.selected_playlist.stem}.json",
            "JSON (*.json)",
        )
        if not chosen:
            return
        data = {
            "path": str(self.selected_playlist.path),
            "stem": self.selected_playlist.stem,
            "duration_90k": int(self.selected_playlist.duration_90k),
            "score": self.selected_playlist.score,
            "confidence": self.selected_playlist.confidence.value,
            "warnings": list(self.selected_playlist.warnings),
            "errors": list(self.selected_playlist.errors),
            "play_items": [
                {
                    "index": item.index,
                    "clip_id": item.clip_id,
                    "in_time_45k": item.in_time_45k,
                    "out_time_45k": item.out_time_45k,
                    "logical_start_90k": int(item.logical_start_90k),
                    "logical_end_90k": int(item.logical_end_90k),
                    "selected_angle": item.selected_angle,
                }
                for item in self.selected_playlist.play_items
            ],
            "marks": [
                {
                    "index": mark.index,
                    "play_item_index": mark.play_item_index,
                    "time_90k": int(mark.time_90k) if mark.time_90k is not None else None,
                }
                for mark in self.selected_playlist.marks
            ],
            "timeline_fingerprint": [
                list(item) for item in self.selected_playlist.timeline_fingerprint
            ],
        }
        try:
            qt_atomic_project_writer(
                Path(chosen),
                (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
        except OSError as error:
            self._record_error(str(error))

    @Slot(str)
    def filter_playlists(self, text: str) -> None:
        wanted = text.strip().casefold()
        for row in range(self.playlist_table.rowCount()):
            item = self.playlist_table.item(row, 0)
            self.playlist_table.setRowHidden(
                row, bool(wanted and item is not None and wanted not in item.text().casefold())
            )

    @Slot()
    def choose_subtitles(self) -> None:
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            self.translations.text("dialog.select_subtitles"),
            str(self.settings.value("recent/subtitles", "")),
            "(*.ass *.ssa *.srt *.sup)",
        )
        if selected:
            self.add_subtitle_paths(tuple(Path(path) for path in selected))

    def add_subtitle_paths(self, paths: tuple[Path, ...]) -> None:
        additions = [path for path in paths if path.suffix.casefold() in SUPPORTED_SUBTITLES]
        if not additions or self.active_task is not None:
            return
        self.subtitle_paths.extend(path for path in additions if path not in self.subtitle_paths)
        request = LoadSubtitlesRequest(tuple(SubtitleInput(path) for path in self.subtitle_paths))
        self._start_task(
            lambda: self.subtitle_service.load_ordered(request),
            self.translations.text("task.loading"),
            self._subtitles_finished,
        )

    def _subtitles_finished(self, value: object) -> None:
        result = cast(LoadSubtitlesResult, value)
        self.subtitle_result = result
        self.prepared = None
        self.mapping_dirty = False
        loaded_paths = {asset.path for asset in result.assets}
        self.subtitle_paths = [path for path in self.subtitle_paths if path in loaded_paths]
        self._populate_mapping_table()
        self._record_issues(result.issues)
        if self.subtitle_paths:
            self.settings.setValue("recent/subtitles", str(self.subtitle_paths[0].parent))
        self.statusBar().showMessage(
            self.translations.text("status.subtitle_complete", count=len(result.assets)), 6000
        )
        self.refresh_output_path()
        self._update_actions()

    def _populate_mapping_table(self) -> None:
        self.mapping_table.setRowCount(0)
        if self.subtitle_result is None:
            return
        for index, asset in enumerate(self.subtitle_result.assets):
            row = self.mapping_table.rowCount()
            self.mapping_table.insertRow(row)
            duration = asset.analysis.effective_end_ticks or 0
            values = (
                str(index + 1),
                asset.path.name,
                asset.format.value,
                format_ticks(duration),
                "",
                "",
                "",
                "0 ms",
                "",
                self.translations.text("mapping.pending"),
                "",
            )
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, str(asset.path))
                self.mapping_table.setItem(row, column, item)

    @Slot()
    def remove_subtitles(self) -> None:
        self._sync_subtitle_order()
        rows = sorted({item.row() for item in self.mapping_table.selectedItems()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self.subtitle_paths):
                self.subtitle_paths.pop(row)
        if self.subtitle_paths:
            self._reload_subtitles()
        else:
            self.subtitle_result = None
            self.mapping_table.setRowCount(0)
            self._update_actions()

    def _reload_subtitles(self) -> None:
        if self.active_task is not None or not self.subtitle_paths:
            return
        request = LoadSubtitlesRequest(tuple(SubtitleInput(path) for path in self.subtitle_paths))
        self._start_task(
            lambda: self.subtitle_service.load_ordered(request),
            self.translations.text("task.loading"),
            self._subtitles_finished,
        )

    def _sync_subtitle_order(self) -> None:
        if self.subtitle_result is None:
            return
        ordered_paths: list[Path] = []
        for row in range(self.mapping_table.rowCount()):
            item = self.mapping_table.item(row, 0)
            if item is not None:
                ordered_paths.append(Path(str(item.data(Qt.ItemDataRole.UserRole))))
        by_path = {asset.path: asset for asset in self.subtitle_result.assets}
        ordered_assets = tuple(by_path[path] for path in ordered_paths if path in by_path)
        if len(ordered_assets) == len(self.subtitle_result.assets):
            self.subtitle_paths = ordered_paths
            self.subtitle_result = replace(self.subtitle_result, assets=ordered_assets)

    @Slot()
    def apply_batch_offset(self) -> None:
        value = self.offset_spin.value()
        rows = {item.row() for item in self.mapping_table.selectedItems()}
        for row in rows:
            path = self._row_path(row)
            item = self.mapping_table.item(row, 7)
            if path is not None and item is not None:
                self.subtitle_offsets_ms[path] = value
                item.setText(f"{value} ms")
        if rows:
            self.mapping_dirty = True

    @Slot()
    def toggle_rows_locked(self) -> None:
        rows = {item.row() for item in self.mapping_table.selectedItems()}
        for row in rows:
            path = self._row_path(row)
            status = self.mapping_table.item(row, 9)
            if path is not None and status is not None:
                locked = path not in self.locked_subtitles
                if locked:
                    self.locked_subtitles.add(path)
                else:
                    self.locked_subtitles.discard(path)
                status.setText(
                    self.translations.text("mapping.locked" if locked else "mapping.pending")
                )
        if rows:
            self.mapping_dirty = True

    def _row_path(self, row: int) -> Path | None:
        item = self.mapping_table.item(row, 0)
        value = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return Path(str(value)) if value else None

    @Slot()
    def choose_output(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            self.translations.text("dialog.select_output"),
            self.output_path.text(),
            "(*.ass *.ssa *.srt *.sup)",
        )
        if selected:
            self.output_mode.setCurrentIndex(self.output_mode.findData("full_path"))
            self.output_path.setText(selected)

    @Slot()
    def choose_output_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self.translations.text("dialog.select_output_directory"),
            self.output_directory.text(),
        )
        if selected:
            self.output_directory.setText(selected)

    @Slot()
    def refresh_output_path(self) -> None:
        if (
            self.selected_playlist is None
            or self.scan_result is None
            or self.scan_result.layout is None
        ):
            return
        output_format = (
            self.subtitle_result.format.value
            if self.subtitle_result is not None and self.subtitle_result.format is not None
            else "ass"
        )
        context = OutputContext(
            subtitle_format=output_format,
            index_bdmv_path=self.scan_result.layout.index_bdmv_path,
            playlist_path=self.selected_playlist.path,
            disc_container_path=self.scan_result.layout.disc_container_path,
        )
        mode = str(self.output_mode.currentData() or "jriver")
        if mode == "full_path":
            return
        target = self._make_target(context, preview=True)
        if target is not None:
            try:
                self.output_path.setText(str(target.resolve_path(context)))
            except ValueError as error:
                self._record_error(str(error))

    def _make_target(self, context: OutputContext, *, preview: bool = False) -> OutputTarget | None:
        policy = CollisionPolicy(str(self.collision_policy.currentData() or "abort"))
        encoding = self.output_encoding.currentText()
        mode = str(self.output_mode.currentData() or "jriver")
        if mode == "jriver":
            return JRiverOutputTarget("primary", policy, encoding)
        if mode == "playlist":
            return PlaylistOutputTarget("primary", policy, encoding)
        if mode == "disc_name":
            directory_text = self.output_directory.text().strip()
            return DiscNameOutputTarget(
                "primary",
                policy,
                encoding,
                Path(directory_text) if directory_text else None,
            )
        selected = (
            Path(self.output_path.text().strip())
            if self.output_path.text().strip()
            else None
        )
        if mode == "custom":
            directory_text = self.output_directory.text().strip()
            if directory_text:
                directory = Path(directory_text)
            elif context.disc_container_path is not None:
                directory = context.disc_container_path.parent
            else:
                if not preview:
                    self.statusBar().showMessage(
                        self.translations.text("status.no_output"), 5000
                    )
                return None
            return TemplateOutputTarget(
                "primary",
                policy,
                encoding,
                directory,
                self.output_template.text().strip(),
            )
        if selected is not None:
            return FullPathOutputTarget("primary", policy, encoding, selected)
        if not preview:
            self.statusBar().showMessage(self.translations.text("status.no_output"), 5000)
        return None

    @Slot()
    def start_preflight(self) -> None:
        request = self._prepare_request()
        if request is None or self.active_task is not None:
            return
        self._start_task(
            lambda: self.merge_service.prepare(request),
            self.translations.text("task.preparing"),
            self._preflight_finished,
        )

    def _prepare_request(self) -> PrepareMergeRequest | None:
        self._sync_subtitle_order()
        if (
            self.scan_result is None
            or self.scan_result.layout is None
            or self.selected_playlist is None
        ):
            self.statusBar().showMessage(self.translations.text("status.no_playlist"), 5000)
            return None
        subtitle_result = self.subtitle_result
        if subtitle_result is None or not subtitle_result.ready:
            self.statusBar().showMessage(self.translations.text("status.no_subtitles"), 5000)
            return None
        subtitle_format = subtitle_result.format
        if subtitle_format is None:
            self.statusBar().showMessage(self.translations.text("status.no_subtitles"), 5000)
            return None
        context = OutputContext(
            subtitle_format=subtitle_format.value,
            index_bdmv_path=self.scan_result.layout.index_bdmv_path,
            playlist_path=self.selected_playlist.path,
            disc_container_path=self.scan_result.layout.disc_container_path,
            input_subtitle_paths=tuple(asset.path for asset in subtitle_result.assets),
        )
        target = self._make_target(context)
        if target is None:
            return None
        return PrepareMergeRequest(
            layout=self.scan_result.layout,
            playlist=self.selected_playlist,
            subtitles=subtitle_result,
            output_targets=(target,),
            output_context=context,
            locks=self._mapping_locks(),
            additional_boundaries=self._additional_boundaries(),
            accept_low_confidence=self.accept_low_confidence.isChecked(),
        )

    def _additional_boundaries(self) -> tuple[TimelineBoundary, ...]:
        return tuple(
            boundary(
                boundary_id,
                time_90k,
                BoundarySource(BoundaryKind.USER, "ui"),
                user_created=True,
            )
            for boundary_id, time_90k in self.timeline.user_boundaries
        )

    def _mapping_locks(self) -> tuple[MappingLock, ...]:
        if self.prepared is None or self.prepared.mapping is None:
            return self.restored_mapping_locks
        locks: list[MappingLock] = []
        for mapping in self.prepared.mapping.mappings:
            path = Path(mapping.subtitle_ref)
            manual_offset_ms = self.subtitle_offsets_ms.get(path, 0)
            if path not in self.locked_subtitles and manual_offset_ms == 0:
                continue
            locks.append(
                MappingLock(
                    mapping.episode_id,
                    mapping.start_boundary.id,
                    mapping.end_boundary.id,
                    MediaTick90k(manual_offset_ms * 90),
                )
            )
        return tuple(locks)

    @Slot(str, int)
    def _user_boundary_changed(self, boundary_id: str, time_90k: int) -> None:
        current_locks = self._mapping_locks()
        updated: list[MappingSnapshot] = []
        invalid_subtitles: set[str] = set()
        for mapping in self.restored_mapping_snapshots:
            start = time_90k if mapping.start_boundary_id == boundary_id else mapping.start_90k
            end = time_90k if mapping.end_boundary_id == boundary_id else mapping.end_90k
            if end <= start:
                invalid_subtitles.add(mapping.subtitle_id)
                continue
            updated.append(replace(mapping, start_90k=start, end_90k=end))
        self.restored_mapping_snapshots = tuple(updated)
        self.restored_mapping_locks = tuple(
            lock
            for lock in current_locks
            if lock.episode_id not in invalid_subtitles
        )
        self.mapping_dirty = True
        self._invalidate_preflight()

    @Slot(str)
    def _user_boundary_deleted(self, boundary_id: str) -> None:
        current_locks = self._mapping_locks()
        removed_subtitles = {
            mapping.subtitle_id
            for mapping in self.restored_mapping_snapshots
            if boundary_id in {mapping.start_boundary_id, mapping.end_boundary_id}
        }
        self.restored_mapping_snapshots = tuple(
            mapping
            for mapping in self.restored_mapping_snapshots
            if mapping.subtitle_id not in removed_subtitles
        )
        self.restored_mapping_locks = tuple(
            lock
            for lock in current_locks
            if lock.episode_id not in removed_subtitles
            and lock.start_boundary_id != boundary_id
            and lock.end_boundary_id != boundary_id
        )
        if self.prepared is not None and self.prepared.mapping is not None:
            for mapping in self.prepared.mapping.mappings:
                if boundary_id in {
                    mapping.start_boundary.id,
                    mapping.end_boundary.id,
                }:
                    self.locked_subtitles.discard(Path(mapping.subtitle_ref))
        self.mapping_dirty = True
        self._invalidate_preflight()

    def _preflight_finished(self, value: object) -> None:
        prepared = cast(PreparedMerge, value)
        self.prepared = prepared
        self.mapping_dirty = False
        lines: list[str] = []
        if prepared.output_preflight is not None:
            lines.extend(str(output.path) for output in prepared.output_preflight.outputs)
        lines.extend(
            f"[{issue.severity.value}] {issue.code}: {issue.message}" for issue in prepared.issues
        )
        if prepared.ready:
            lines.insert(0, self.translations.text("preflight.ready"))
        self.preflight_summary.setPlainText("\n".join(lines))
        self._record_issues(prepared.issues)
        self._populate_prepared_mapping(prepared)
        self._update_actions()

    def _populate_prepared_mapping(self, prepared: PreparedMerge) -> None:
        if prepared.mapping is None:
            return
        rows_by_path = {
            path: row
            for row in range(self.mapping_table.rowCount())
            if (path := self._row_path(row)) is not None
        }
        for mapping in prepared.mapping.mappings:
            row = rows_by_path.get(Path(mapping.subtitle_ref))
            if row is None:
                continue
            path = Path(mapping.subtitle_ref)
            if mapping.locked:
                self.locked_subtitles.add(path)
            self.subtitle_offsets_ms[path] = int(mapping.manual_offset_90k) // 90
            values = (
                mapping.start_boundary.id,
                mapping.end_boundary.id,
                format_ticks(int(mapping.interval_duration_90k)),
                f"{int(mapping.manual_offset_90k) // 90} ms",
                mapping.confidence.value,
                self.translations.text("mapping.locked" if mapping.locked else "mapping.ready"),
                "; ".join(mapping.warnings),
            )
            for column, text in zip(range(4, 11), values, strict=True):
                item = self.mapping_table.item(row, column)
                if item is not None:
                    item.setText(text)

    @Slot()
    def start_generate(self) -> None:
        if self.mapping_dirty or self.prepared is None or not self.prepared.ready:
            self.start_preflight()
            return
        request = ExecuteMergeRequest(self.prepared)
        self._start_task(
            lambda: self.merge_service.execute(request),
            self.translations.text("task.writing"),
            self._generate_finished,
        )

    def _generate_finished(self, value: object) -> None:
        result = cast(ExecuteMergeResult, value)
        self._record_issues(result.issues)
        count = len(result.receipt.paths) if result.receipt is not None else 0
        self.statusBar().showMessage(self.translations.text("status.written", count=count), 8000)

    def _start_task(
        self,
        operation: Callable[[], object],
        status: str,
        success: Callable[[object], None],
    ) -> None:
        if self.active_task is not None:
            return
        self.cancellation = CancellationToken()
        task: ServiceTask[object] = ServiceTask(operation, token=self.cancellation)
        task.signals.progress.connect(self._task_progress)
        task.signals.succeeded.connect(success)
        task.signals.failed.connect(self._task_failed)
        task.signals.cancelled.connect(self._task_cancelled)
        task.signals.finished.connect(self._task_finished)
        self.active_task = task
        self.task_status.setText(status)
        self.progress.setValue(0)
        self.cancel_button.setEnabled(True)
        self._update_actions()
        self.thread_pool.start(task)

    @Slot(int, str)
    def _task_progress(self, value: int, detail: str) -> None:
        del detail
        self.progress.setValue(value)
        self.progress.setFormat("%p%")

    @Slot(str, str)
    def _task_failed(self, message: str, details: str) -> None:
        self._record_error(f"{message}\n{details}")

    @Slot()
    def _task_cancelled(self) -> None:
        self.task_status.setText(self.translations.text("task.cancelled"))

    @Slot()
    def _task_finished(self) -> None:
        was_cancelled = self.cancellation is not None and self.cancellation.cancelled
        self.active_task = None
        self.cancellation = None
        self.cancel_button.setEnabled(False)
        self.progress.setValue(100)
        if not was_cancelled:
            self.task_status.setText(self.translations.text("task.complete"))
        self._update_actions()
        if self.pending_restore_after_scan:
            self.pending_restore_after_scan = False
            self._continue_project_restore()

    @Slot()
    def cancel_active_task(self) -> None:
        if self.cancellation is not None:
            self.cancellation.cancel()
        self.cancel_button.setEnabled(False)

    def _record_issues(self, issues: tuple[ApplicationIssue, ...]) -> None:
        for issue in issues:
            self._record_error(
                f"[{issue.severity.value}] {issue.code}: {issue.message}"
                + (f" ({issue.source})" if issue.source else "")
            )

    def _record_error(self, message: str) -> None:
        self.error_details.append(message)
        self.error_panel.setPlainText("\n\n".join(self.error_details))
        self.details_button.setEnabled(True)

    def _show_timeline(self) -> None:
        self.timeline.show_playlist(
            self.selected_playlist,
            item_label=self.translations.text("timeline.item"),
            chapter_label=self.translations.text("timeline.chapter"),
            empty_text=self.translations.text("timeline.empty"),
        )
        self.timeline.setToolTip(self.translations.text("timeline.boundary_add"))

    def _invalidate_preflight(self) -> None:
        self.prepared = None
        self.preflight_summary.setPlainText(self.translations.text("preflight.waiting"))
        self._update_actions()

    @Slot(bool)
    def toggle_advanced(self, visible: bool) -> None:
        self.advanced_panel.setVisible(visible)
        self.advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
        )

    def _update_actions(self) -> None:
        idle = self.active_task is None
        has_playlist = self.selected_playlist is not None
        has_subtitles = self.subtitle_result is not None and self.subtitle_result.ready
        self.scan_button.setEnabled(idle and bool(self.path_edit.text().strip()))
        self.add_subtitle_button.setEnabled(idle)
        self.auto_map_button.setEnabled(idle and has_playlist and has_subtitles)
        self.preflight_button.setEnabled(idle and has_playlist and has_subtitles)
        self.generate_button.setEnabled(idle and self.prepared is not None and self.prepared.ready)
        self.remove_subtitle_button.setEnabled(idle and bool(self.subtitle_paths))
        self.open_button.setEnabled(idle)
        self.save_button.setEnabled(idle and has_playlist and has_subtitles)

    def set_language(self, locale: str) -> None:
        self.translations.set_locale(locale)
        self.settings.setValue("ui/language", locale)
        self.retranslate_ui()

    def set_theme(self, mode: ThemeMode) -> None:
        application = QApplication.instance()
        if isinstance(application, QApplication):
            apply_theme(application, mode)
        self.settings.setValue("ui/theme", mode.value)
        self.theme_system.setChecked(mode is ThemeMode.SYSTEM)
        self.theme_light.setChecked(mode is ThemeMode.LIGHT)
        self.theme_dark.setChecked(mode is ThemeMode.DARK)

    def _restore_settings(self) -> None:
        geometry = self.settings.value("ui/geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        self.path_edit.setText(str(self.settings.value("recent/bdmv", "")))
        output_mode = str(self.settings.value("output/mode", "jriver"))
        self.output_mode.setProperty("restoredMode", output_mode)
        try:
            theme = ThemeMode(str(self.settings.value("ui/theme", ThemeMode.SYSTEM.value)))
        except ValueError:
            theme = ThemeMode.SYSTEM
        self.set_theme(theme)

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        if self.cancellation is not None:
            self.cancellation.cancel()
        self.settings.setValue("ui/geometry", self.saveGeometry())
        self.settings.setValue("ui/language", self.translations.locale)
        self.settings.setValue("output/mode", self.output_mode.currentData())
        super().closeEvent(event)

    @override
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    @override
    def dropEvent(self, event: QDropEvent) -> None:
        paths = tuple(
            Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()
        )
        subtitles = tuple(path for path in paths if path.suffix.casefold() in SUPPORTED_SUBTITLES)
        directories = tuple(path for path in paths if path.is_dir())
        if subtitles:
            self.add_subtitle_paths(subtitles)
            event.acceptProposedAction()
        elif directories:
            self.path_edit.setText(str(directories[0]))
            self.start_scan()
            event.acceptProposedAction()
        else:
            self.statusBar().showMessage(
                self.translations.text("dialog.unsupported_drop"), 6000
            )
