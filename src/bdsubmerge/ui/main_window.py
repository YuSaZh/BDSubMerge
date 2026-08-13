"""Single-window workspace driven exclusively by application services."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast, override

from PySide6.QtCore import (
    QByteArray,
    QItemSelectionModel,
    QPoint,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
)
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
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
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
    ApplicationSeverity,
    BdmvApplicationService,
    ExecuteMergeRequest,
    ExecuteMergeResult,
    ImportSubtitlesRequest,
    ImportSubtitlesResult,
    LoadSubtitlesRequest,
    LoadSubtitlesResult,
    MergeApplicationService,
    MergeReportFormat,
    MergeReportTarget,
    PlaylistSelectionRequest,
    PlaylistSelectionResult,
    PreparedMerge,
    PrepareMergeRequest,
    ScanRequest,
    ScanResult,
    SubtitleApplicationService,
    SubtitleAsset,
    SubtitleInput,
    build_playlist_boundaries,
    natural_path_key,
    select_playlists,
)
from bdsubmerge.application.display_models import (
    build_playlist_structure,
    build_subtitle_details,
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
from bdsubmerge.subtitles import SubtitleFormat

from .details import (
    ReadOnlyDetailsDialog,
    format_playlist_details,
    format_subtitle_details,
)
from .project_io import capture_and_save, load_restored_project, qt_atomic_project_writer
from .tasks import CancellationToken, ServiceTask
from .theme import ThemeMode, apply_theme
from .timeline import (
    TimeDisplayFormat,
    TimelineEpisode,
    TimelineView,
    format_media_time,
    format_ticks,
)
from .translations import TranslationCatalog


class SubtitleMappingTable(QTableWidget):
    rows_reordered = Signal(object, int)

    @override
    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        del supported_actions
        super().startDrag(Qt.DropAction.CopyAction)

    def _accept_internal_reorder(self, event: QDropEvent) -> bool:
        accepted = (
            event.source() is self
            and event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist")
            and bool(event.possibleActions() & Qt.DropAction.CopyAction)
        )
        if accepted:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()
        return accepted

    @override
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        self._accept_internal_reorder(event)

    @override
    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        self._accept_internal_reorder(event)

    @override
    def dropEvent(self, event: QDropEvent) -> None:
        if not self._accept_internal_reorder(event):
            return
        source_rows = tuple(
            sorted(index.row() for index in self.selectionModel().selectedRows(0))
        )
        if not source_rows:
            event.ignore()
            return

        position = event.position().toPoint()
        target = self.indexAt(position)
        if target.isValid():
            target_rect = self.visualRect(target)
            insert_at = target.row() + int(position.y() >= target_rect.center().y())
        else:
            insert_at = self.rowCount()
        self.rows_reordered.emit(source_rows, insert_at)


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
        self.preflight_revision = 0
        self.active_preflight_revision: int | None = None
        self.pending_preflight = False
        self.mapping_preflight_timer = QTimer(self)
        self.mapping_preflight_timer.setSingleShot(True)
        self.project_path: Path | None = None
        self.pending_project_path: Path | None = None
        self.pending_project_previous_bdmv = ""
        self.restored_mapping_locks: tuple[MappingLock, ...] = ()
        self.restored_mapping_snapshots: tuple[MappingSnapshot, ...] = ()
        self.pending_project: RestoredProject | None = None
        self.pending_restore_after_scan = False
        self.pending_bdmv_scan_path: Path | None = None
        self.pending_import_bdmv_fallback = False
        self.subtitle_paths: list[Path] = []
        self.locked_subtitles: set[Path] = set()
        self.subtitle_offsets_90k: dict[Path, int] = {}
        self.output_states = [
            OutputState(
                "primary",
                "jriver",
                "",
                None,
                "utf-8-sig",
                CollisionPolicy.ABORT.value,
            )
        ]
        self.editing_output_id = "primary"
        self.loading_output_editor = False
        self.default_report_path: Path | None = None
        self.error_details: list[str] = []
        self.active_task_kind = ""
        self.task_failed = False
        self.task_cancelled = False
        self.details_dialog: ReadOnlyDetailsDialog | None = None

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
        self.timeline_format = QComboBox()
        self.timeline_format.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        timeline_header = QHBoxLayout()
        timeline_header.addWidget(self.timeline_title)
        timeline_header.addStretch()
        timeline_header.addWidget(self.timeline_format)
        self.timeline = TimelineView()
        self.timeline.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        timeline_layout.addLayout(timeline_header)
        timeline_layout.addWidget(self.timeline)
        upper.addWidget(playlist_widget)
        upper.addWidget(timeline_widget)
        upper.setSizes([430, 650])
        root.addWidget(upper, 2)

        self.subtitle_group = QGroupBox()
        subtitle_layout = QVBoxLayout(self.subtitle_group)
        subtitle_toolbar = QHBoxLayout()
        self.add_subtitle_button = QPushButton()
        self.add_subtitle_directory_button = QPushButton()
        self.remove_subtitle_button = QPushButton()
        self.move_subtitle_up_button = QPushButton()
        self.move_subtitle_down_button = QPushButton()
        self.natural_sort_button = QPushButton()
        self.offset_button = QPushButton()
        self.lock_button = QPushButton()
        self.reset_mapping_button = QPushButton()
        subtitle_toolbar.addWidget(self.add_subtitle_button)
        subtitle_toolbar.addWidget(self.add_subtitle_directory_button)
        subtitle_toolbar.addWidget(self.remove_subtitle_button)
        subtitle_toolbar.addWidget(self.move_subtitle_up_button)
        subtitle_toolbar.addWidget(self.move_subtitle_down_button)
        subtitle_toolbar.addWidget(self.natural_sort_button)
        subtitle_toolbar.addWidget(self.offset_button)
        subtitle_toolbar.addWidget(self.lock_button)
        subtitle_toolbar.addWidget(self.reset_mapping_button)
        subtitle_toolbar.addStretch()
        self.mapping_table = SubtitleMappingTable(0, 11)
        self.mapping_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mapping_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.mapping_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.mapping_table.setDragDropMode(QTableWidget.DragDropMode.DragDrop)
        self.mapping_table.setDragEnabled(True)
        self.mapping_table.setAcceptDrops(True)
        self.mapping_table.setDragDropOverwriteMode(False)
        self.mapping_table.setDefaultDropAction(Qt.DropAction.CopyAction)
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
        output_editor = QVBoxLayout()
        output_editor.addLayout(output_form)
        self.output_targets_label = QLabel()
        self.output_targets_table = QTableWidget(0, 7)
        self.output_targets_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.output_targets_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.output_targets_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.output_targets_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.output_targets_table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.Stretch,
        )
        self.output_targets_table.horizontalHeader().setStretchLastSection(False)
        self.output_targets_table.setMaximumHeight(130)
        output_target_actions = QHBoxLayout()
        self.add_output_target_button = QPushButton()
        self.remove_output_target_button = QPushButton()
        output_target_actions.addWidget(self.add_output_target_button)
        output_target_actions.addWidget(self.remove_output_target_button)
        output_target_actions.addStretch()
        output_editor.addWidget(self.output_targets_label)
        output_editor.addWidget(self.output_targets_table)
        output_editor.addLayout(output_target_actions)

        report_form = QFormLayout()
        self.report_enabled = QCheckBox()
        self.report_format = QComboBox()
        self.report_path = QLineEdit()
        self.report_path.setClearButtonEnabled(True)
        self.report_browse = QPushButton()
        report_path_layout = QHBoxLayout()
        report_path_layout.addWidget(self.report_path, 1)
        report_path_layout.addWidget(self.report_browse)
        self.report_collision_policy = QComboBox()
        self.report_format_label = QLabel()
        self.report_path_label = QLabel()
        self.report_collision_label = QLabel()
        report_form.addRow(self.report_enabled)
        report_form.addRow(self.report_format_label, self.report_format)
        report_form.addRow(self.report_path_label, report_path_layout)
        report_form.addRow(self.report_collision_label, self.report_collision_policy)
        output_editor.addLayout(report_form)
        output_layout.addLayout(output_editor, 3)
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
        self.task_detail = QLabel()
        self.task_detail.setMinimumWidth(0)
        self.task_detail.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.cancel_button = QPushButton()
        self.cancel_button.setEnabled(False)
        self.details_button = QPushButton()
        self.details_button.setCheckable(True)
        task_row.addWidget(self.task_status)
        task_row.addWidget(self.task_detail, 1)
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
        self.mapping_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def _connect_signals(self) -> None:
        self.choose_path_button.clicked.connect(self.choose_bdmv)
        self.open_button.clicked.connect(self.open_project)
        self.save_button.clicked.connect(self.save_project)
        self.scan_button.clicked.connect(self.start_scan)
        self.path_edit.returnPressed.connect(self.start_scan)
        self.playlist_search.textChanged.connect(self.filter_playlists)
        self.playlist_table.itemSelectionChanged.connect(self.select_playlist)
        self.playlist_table.cellDoubleClicked.connect(self.show_playlist_details)
        self.primary_playlist_combo.currentIndexChanged.connect(
            self.select_primary_playlist
        )
        self.timeline_format.currentIndexChanged.connect(self.change_timeline_format)
        self.add_subtitle_button.clicked.connect(self.choose_subtitles)
        self.add_subtitle_directory_button.clicked.connect(
            self.choose_subtitle_directory
        )
        self.remove_subtitle_button.clicked.connect(self.remove_subtitles)
        self.move_subtitle_up_button.clicked.connect(
            lambda: self.move_selected_subtitles(-1)
        )
        self.move_subtitle_down_button.clicked.connect(
            lambda: self.move_selected_subtitles(1)
        )
        self.natural_sort_button.clicked.connect(self.restore_natural_subtitle_order)
        self.offset_button.clicked.connect(self.apply_batch_offset)
        self.lock_button.clicked.connect(self.toggle_rows_locked)
        self.reset_mapping_button.clicked.connect(self.reset_automatic_mapping)
        self.mapping_table.cellDoubleClicked.connect(self.show_subtitle_details)
        self.mapping_table.itemSelectionChanged.connect(
            self.select_timeline_episode_from_table
        )
        self.mapping_table.rows_reordered.connect(self._mapping_table_rows_reordered)
        self.output_mode.currentIndexChanged.connect(self.output_mode_changed)
        self.output_browse.clicked.connect(self.choose_output)
        self.output_directory_browse.clicked.connect(self.choose_output_directory)
        self.collision_policy.currentIndexChanged.connect(self._output_editor_changed)
        self.output_encoding.currentIndexChanged.connect(self._output_editor_changed)
        self.output_path.textChanged.connect(self._output_editor_changed)
        self.output_directory.textChanged.connect(self.output_configuration_changed)
        self.output_template.textChanged.connect(self.output_configuration_changed)
        self.output_targets_table.itemSelectionChanged.connect(
            self.select_output_target
        )
        self.add_output_target_button.clicked.connect(self.add_output_target)
        self.remove_output_target_button.clicked.connect(self.remove_output_target)
        self.report_enabled.toggled.connect(self._report_configuration_changed)
        self.report_format.currentIndexChanged.connect(
            self._report_configuration_changed
        )
        self.report_path.textChanged.connect(self._invalidate_preflight)
        self.report_collision_policy.currentIndexChanged.connect(
            self._invalidate_preflight
        )
        self.report_browse.clicked.connect(self.choose_report)
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
        self.timeline.episode_selected.connect(self.select_mapping_row_from_timeline)
        self.timeline.episode_boundary_moved.connect(self.move_episode_boundary)
        self.mapping_preflight_timer.timeout.connect(self.start_preflight)
        self.playlist_table.customContextMenuRequested.connect(self.show_playlist_context_menu)
        self.mapping_table.customContextMenuRequested.connect(self.show_subtitle_context_menu)
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
        self._reset_combo(
            self.timeline_format,
            (
                (tr("timeline.format_clock"), TimeDisplayFormat.CLOCK.value),
                (tr("timeline.format_timecode"), TimeDisplayFormat.TIMECODE.value),
                (tr("timeline.format_ticks"), TimeDisplayFormat.TICKS.value),
            ),
        )
        self.subtitle_group.setTitle(tr("subtitles.title"))
        self.add_subtitle_button.setText(tr("subtitles.add"))
        self.add_subtitle_directory_button.setText(tr("subtitles.add_directory"))
        self.remove_subtitle_button.setText(tr("subtitles.remove"))
        self.move_subtitle_up_button.setText(tr("subtitles.move_up"))
        self.move_subtitle_down_button.setText(tr("subtitles.move_down"))
        self.natural_sort_button.setText(tr("subtitles.natural_sort"))
        self.offset_button.setText(tr("subtitles.offset"))
        self.lock_button.setText(tr("subtitles.lock"))
        self.reset_mapping_button.setText(tr("subtitles.reset_mapping"))
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
        self.output_targets_label.setText(tr("output.targets"))
        self.output_targets_table.setHorizontalHeaderLabels(
            (
                tr("output.target_id"),
                tr("output.mode"),
                tr("output.path"),
                tr("output.format"),
                tr("output.encoding"),
                tr("output.collision"),
                tr("output.backup"),
            )
        )
        self.add_output_target_button.setText(tr("output.add_target"))
        self.remove_output_target_button.setText(tr("output.remove_target"))
        self.output_browse.setText(tr("common.browse"))
        self.output_directory_browse.setText(tr("common.browse"))
        self.report_enabled.setText(tr("report.enabled"))
        self.report_format_label.setText(tr("report.format"))
        self.report_path_label.setText(tr("report.path"))
        self.report_collision_label.setText(tr("report.collision"))
        self.report_browse.setText(tr("common.browse"))
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
        self._reset_combo(
            self.report_format,
            (
                (tr("report.json"), MergeReportFormat.JSON.value),
                (tr("report.text"), MergeReportFormat.TEXT.value),
            ),
        )
        self._reset_combo(
            self.report_collision_policy,
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
        self._update_report_controls()
        self._populate_output_targets()
        self._show_timeline()
        self._update_actions()

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
    def change_timeline_format(self) -> None:
        value = str(self.timeline_format.currentData() or TimeDisplayFormat.CLOCK.value)
        self.timeline.set_time_format(TimeDisplayFormat(value))
        self._refresh_mapping_boundary_controls()

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
            kind="project_scan" if self.pending_project is not None else "scan",
        )

    def _scan_finished(self, value: object) -> None:
        result = cast(ScanResult, value)
        previous_bdmv_path = (
            self.scan_result.layout.bdmv_path
            if self.scan_result is not None and self.scan_result.layout is not None
            else None
        )
        if not result.ready:
            self.task_failed = True
            self.task_status.setText(self.translations.text("task.failed"))
        if self.pending_project is not None and not result.ready:
            self._record_issues(result.issues)
            self.path_edit.setText(self.pending_project_previous_bdmv)
            self._discard_pending_project_restore()
            self.statusBar().showMessage(
                self.translations.text("status.project_incomplete"), 8000
            )
            self._update_actions()
            return
        if self.pending_project is not None:
            self.project_path = None
        elif (
            self.project_path is not None
            and result.layout is not None
            and previous_bdmv_path != result.layout.bdmv_path
        ):
            self.project_path = None
        self._clear_playlist_mapping()
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
        elif not result.playlists:
            self._invalidate_preflight(preserve_mapping=False)

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
        if self.loading_output_editor:
            return
        self._refresh_playlist_selection()
        self._update_output_controls()
        self._invalidate_preflight()
        self._show_timeline()
        self.refresh_output_path()
        self._store_current_output_state()
        self._populate_output_targets()

    @Slot()
    def output_configuration_changed(self) -> None:
        if self.loading_output_editor:
            return
        self._invalidate_preflight()
        self.refresh_output_path()
        self._store_current_output_state()
        self._populate_output_targets()

    @Slot()
    def _output_editor_changed(self) -> None:
        if self.loading_output_editor:
            return
        self._store_current_output_state()
        self._populate_output_targets()
        self._invalidate_preflight()

    def _editor_output_state(self, target_id: str | None = None) -> OutputState:
        preset = str(self.output_mode.currentData() or "jriver")
        collision = str(
            self.collision_policy.currentData() or CollisionPolicy.ABORT.value
        )
        resolved = Path(self.output_path.text()) if self.output_path.text().strip() else None
        template = self.output_template.text().strip() if preset == "custom" else ""
        return OutputState(
            target_id or self.editing_output_id,
            preset,
            template,
            resolved,
            self.output_encoding.currentText(),
            collision,
            "backup" if collision == CollisionPolicy.BACKUP.value else "none",
        )

    def _store_current_output_state(self) -> None:
        if self.loading_output_editor:
            return
        current = self._editor_output_state()
        for index, state in enumerate(self.output_states):
            if state.id == self.editing_output_id:
                self.output_states[index] = current
                return
        self.output_states.append(current)

    def _load_output_editor(self, state: OutputState) -> None:
        self.loading_output_editor = True
        self.editing_output_id = state.id
        try:
            mode_index = self.output_mode.findData(state.preset)
            if mode_index >= 0:
                self.output_mode.setCurrentIndex(mode_index)
            policy_index = self.collision_policy.findData(state.collision_policy)
            if policy_index >= 0:
                self.collision_policy.setCurrentIndex(policy_index)
            encoding_index = self.output_encoding.findText(state.encoding)
            if encoding_index >= 0:
                self.output_encoding.setCurrentIndex(encoding_index)
            self.output_template.setText(
                state.path_template
                if state.preset == "custom" and state.path_template
                else "{disc_name}_{playlist_stem}.{format}"
            )
            self.output_directory.clear()
            if state.resolved_path is not None:
                if state.preset in {"disc_name", "custom"}:
                    self.output_directory.setText(str(state.resolved_path.parent))
                self.output_path.setText(str(state.resolved_path))
            else:
                self.output_path.clear()
        finally:
            self.loading_output_editor = False
        self._update_output_controls()

    def _populate_output_targets(self) -> None:
        selected_id = self.editing_output_id
        subtitle_format = (
            self.subtitle_result.format
            if self.subtitle_result is not None
            else None
        )
        output_format = (
            subtitle_format.value
            if subtitle_format is not None
            else self.translations.text("common.unknown")
        )
        self.output_targets_table.blockSignals(True)
        self.output_targets_table.setRowCount(0)
        selected_row = 0
        for row, state in enumerate(self.output_states):
            self.output_targets_table.insertRow(row)
            mode_index = self.output_mode.findData(state.preset)
            mode_label = (
                self.output_mode.itemText(mode_index) if mode_index >= 0 else state.preset
            )
            collision_index = self.collision_policy.findData(state.collision_policy)
            collision_label = (
                self.collision_policy.itemText(collision_index)
                if collision_index >= 0
                else state.collision_policy
            )
            values = (
                state.id,
                mode_label,
                str(state.resolved_path or ""),
                output_format,
                (
                    self.translations.text("common.binary")
                    if subtitle_format is SubtitleFormat.SUP
                    else state.encoding
                ),
                collision_label,
                self.translations.text(
                    "common.yes"
                    if state.collision_policy == CollisionPolicy.BACKUP.value
                    else "common.no"
                ),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, state.id)
                self.output_targets_table.setItem(row, column, item)
            if state.id == selected_id:
                selected_row = row
        if self.output_states:
            self.output_targets_table.selectRow(selected_row)
        self.output_targets_table.blockSignals(False)
        self.remove_output_target_button.setEnabled(len(self.output_states) > 1)

    @Slot()
    def select_output_target(self) -> None:
        rows = self.output_targets_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.output_targets_table.item(rows[0].row(), 0)
        target_id = str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else ""
        if not target_id or target_id == self.editing_output_id:
            return
        self._store_current_output_state()
        state = next((item for item in self.output_states if item.id == target_id), None)
        if state is None:
            return
        self._load_output_editor(state)
        self._invalidate_preflight()

    @Slot()
    def add_output_target(self) -> None:
        self._store_current_output_state()
        used_ids = {state.id for state in self.output_states}
        index = 2
        while f"output-{index}" in used_ids:
            index += 1
        state = OutputState(
            f"output-{index}",
            "full_path",
            "",
            None,
            self.output_encoding.currentText(),
            str(self.collision_policy.currentData() or CollisionPolicy.ABORT.value),
        )
        self.output_states.append(state)
        self._load_output_editor(state)
        self._populate_output_targets()
        self._refresh_playlist_selection()
        self._invalidate_preflight()

    @Slot()
    def remove_output_target(self) -> None:
        if len(self.output_states) <= 1:
            return
        self.output_states = [
            state for state in self.output_states if state.id != self.editing_output_id
        ]
        self._load_output_editor(self.output_states[0])
        self._populate_output_targets()
        self._refresh_playlist_selection()
        self._invalidate_preflight()

    def _update_output_controls(self) -> None:
        mode = str(self.output_mode.currentData() or "jriver")
        idle = self.active_task is None
        has_directory = mode in {"disc_name", "custom"}
        has_template = mode == "custom"
        self.output_directory_label.setVisible(has_directory)
        self.output_directory_row.setVisible(has_directory)
        self.output_template_label.setVisible(has_template)
        self.output_template.setVisible(has_template)
        self.output_path.setReadOnly(mode != "full_path")
        self.output_browse.setEnabled(idle and mode == "full_path")

    def _refresh_playlist_selection(self, *, rebuild_primary: bool = True) -> None:
        previous_playlist_path = (
            self.selected_playlist.path if self.selected_playlist is not None else None
        )
        if not self.selected_playlists:
            self.playlist_selection = None
            self.selected_playlist = None
            self.primary_playlist_row.setVisible(False)
            self.playlist_compatibility.setVisible(False)
            self.playlist_warning.setVisible(False)
            if previous_playlist_path is not None:
                self._clear_playlist_mapping()
            return
        self._store_current_output_state()
        uses_jriver = any(state.preset == "jriver" for state in self.output_states)
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
        selected_playlist_path = (
            self.selected_playlist.path if self.selected_playlist is not None else None
        )
        if selected_playlist_path != previous_playlist_path:
            self._clear_playlist_mapping()

    def _clear_playlist_mapping(self) -> None:
        self._clear_mapping_constraints()
        self.subtitle_offsets_90k.clear()
        self.timeline.set_user_boundaries(())
        self.mapping_dirty = self.subtitle_result is not None
        self._populate_mapping_table()

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
        self.pending_project = restored
        self.pending_project_path = project_path
        self.pending_project_previous_bdmv = self.path_edit.text()
        self._show_source_checks(restored)
        self.path_edit.setText(str(restored.state.bdmv_path))
        self.start_scan()

    def _project_state(self) -> ProjectState:
        assert self.scan_result is not None and self.scan_result.layout is not None
        assert self.selected_playlist is not None and self.subtitle_result is not None
        boundaries = self._project_boundaries()
        mappings = self._project_mappings()
        self._store_current_output_state()
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
            outputs=tuple(self.output_states),
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
        if self.prepared is not None and self.prepared.mapping is not None:
            snapshots = tuple(
                MappingSnapshot(
                    item.episode_id,
                    item.start_boundary.id,
                    item.end_boundary.id,
                    int(item.start_boundary.time_90k),
                    int(item.end_boundary.time_90k),
                    int(item.manual_offset_90k),
                    item.locked,
                    item.confidence.value,
                    item.warnings,
                )
                for item in self.prepared.mapping.mappings
            )
        else:
            snapshots = self.restored_mapping_snapshots
        locks_by_episode = {
            item.episode_id: item for item in self._mapping_locks()
        }
        boundaries = self._boundary_by_id()
        current: list[MappingSnapshot] = []
        for snapshot in snapshots:
            row = self._row_for_episode(snapshot.subtitle_id)
            path = self._row_path(row) if row is not None else None
            lock = locks_by_episode.get(snapshot.subtitle_id)
            start_id = (
                lock.start_boundary_id
                if lock is not None
                else snapshot.start_boundary_id
            )
            end_id = (
                lock.end_boundary_id
                if lock is not None
                else snapshot.end_boundary_id
            )
            start = boundaries.get(start_id)
            end = boundaries.get(end_id)
            manual_offset_90k = (
                int(lock.manual_offset_90k)
                if lock is not None
                else snapshot.manual_offset_90k
            )
            if path is not None:
                manual_offset_90k = self.subtitle_offsets_90k.get(
                    path,
                    manual_offset_90k,
                )
            current.append(
                replace(
                    snapshot,
                    start_boundary_id=start_id,
                    end_boundary_id=end_id,
                    start_90k=(
                        int(start.time_90k)
                        if start is not None
                        else snapshot.start_90k
                    ),
                    end_90k=(
                        int(end.time_90k)
                        if end is not None
                        else snapshot.end_90k
                    ),
                    manual_offset_90k=manual_offset_90k,
                    locked=(
                        lock is not None
                        or (path is not None and path in self.locked_subtitles)
                    ),
                )
            )
        return tuple(current)

    def _project_output_state(self) -> OutputState:
        self._store_current_output_state()
        return next(
            state for state in self.output_states if state.id == self.editing_output_id
        )

    def _restore_output_states(self, outputs: tuple[OutputState, ...]) -> None:
        if not outputs:
            return
        self.output_states = list(outputs)
        self._load_output_editor(self.output_states[0])
        self._populate_output_targets()
        self._refresh_playlist_selection()
        self._invalidate_preflight()

    def _continue_project_restore(self) -> None:
        assert self.pending_project is not None
        if self.selected_playlist is None:
            self._discard_pending_project_restore()
            self.statusBar().showMessage(
                self.translations.text("status.project_incomplete"), 8000
            )
            return
        state = self.pending_project.state
        self.project_notes.setText(state.ui_notes)
        self._restore_output_states(state.outputs)
        user_boundaries = tuple(
            (item.id, item.time_90k) for item in state.boundaries if item.user_created
        )
        self.timeline.set_user_boundaries(user_boundaries)
        ordered_subtitles = tuple(sorted(state.subtitles, key=lambda item: item.order))
        existing_subtitles = tuple(
            item for item in ordered_subtitles if item.path.is_file()
        )
        self.subtitle_paths = [item.path for item in existing_subtitles]
        self.subtitle_result = None
        self.mapping_table.setRowCount(0)
        self.locked_subtitles.clear()
        self.subtitle_offsets_90k.clear()
        self.restored_mapping_locks = ()
        self.restored_mapping_snapshots = ()
        self.prepared = None
        self.mapping_dirty = False
        if existing_subtitles:
            request = LoadSubtitlesRequest(
                tuple(
                    SubtitleInput(item.path, item.encoding or None)
                    for item in existing_subtitles
                )
            )
            self._start_task(
                lambda: self.subtitle_service.load_ordered(request),
                self.translations.text("task.loading"),
                self._project_subtitles_finished,
                kind="project_subtitles",
            )
        else:
            self._discard_pending_project_restore()
            self.statusBar().showMessage(
                self.translations.text("status.project_incomplete"), 8000
            )

    def _project_subtitles_finished(self, value: object) -> None:
        result = cast(LoadSubtitlesResult, value)
        self._subtitles_finished(result)
        if self.pending_project is None:
            return
        if not result.ready:
            self.task_failed = True
            self.task_status.setText(self.translations.text("task.failed"))
            self._discard_pending_project_restore()
            self.statusBar().showMessage(
                self.translations.text("status.project_incomplete"), 8000
            )
            return
        state = self.pending_project.state
        saved_subtitles_by_path = {item.path: item for item in state.subtitles}
        restored_mappings_by_id = {
            item.subtitle_id: item for item in state.mappings
        }
        remapped_snapshots: list[MappingSnapshot] = []
        restored_rows: list[tuple[int, SubtitleState, MappingSnapshot]] = []
        for row in range(self.mapping_table.rowCount()):
            row_path = self._row_path(row)
            saved_subtitle = (
                saved_subtitles_by_path.get(row_path) if row_path is not None else None
            )
            saved_mapping = (
                restored_mappings_by_id.get(saved_subtitle.id)
                if saved_subtitle is not None
                else None
            )
            if saved_subtitle is None or saved_mapping is None:
                continue
            current_episode_id = f"episode-{row + 1}"
            remapped = replace(saved_mapping, subtitle_id=current_episode_id)
            remapped_snapshots.append(remapped)
            restored_rows.append((row, saved_subtitle, remapped))
        self.restored_mapping_locks = tuple(
            MappingLock(
                item.subtitle_id,
                item.start_boundary_id,
                item.end_boundary_id,
                MediaTick90k(item.manual_offset_90k),
            )
            for item in remapped_snapshots
            if item.locked
        )
        self.restored_mapping_snapshots = tuple(remapped_snapshots)
        for row, subtitle, mapping in restored_rows:
            path = subtitle.path
            if mapping.locked:
                self.locked_subtitles.add(path)
            self.subtitle_offsets_90k[path] = mapping.manual_offset_90k
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
        self._refresh_mapping_boundary_controls()
        self._show_timeline()
        self._update_actions()
        incomplete = self.pending_project.has_changed_sources
        project_path = self.pending_project_path
        if project_path is not None:
            self.project_path = project_path
            self.settings.setValue("recent/project", str(project_path))
        self.pending_project = None
        self.pending_project_path = None
        self.pending_project_previous_bdmv = ""
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
        row = self.playlist_table.rowAt(position.y())
        playlist = self._playlist_at_row(row)
        if playlist is None:
            return
        menu = QMenu(self)
        details_action = menu.addAction(self.translations.text("playlist.details"))
        export_action = menu.addAction(self.translations.text("playlist.export"))
        selected = menu.exec(self.playlist_table.viewport().mapToGlobal(position))
        if selected is details_action:
            self._show_playlist_details(playlist)
        elif selected is export_action:
            self.export_playlist_info(playlist)

    def export_playlist_info(self, playlist: PlaylistInfo | None = None) -> None:
        playlist = playlist or self.selected_playlist
        if playlist is None:
            return
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            self.translations.text("playlist.export_title"),
            f"{playlist.stem}.json",
            "JSON (*.json)",
        )
        if not chosen:
            return
        data = {
            "path": str(playlist.path),
            "stem": playlist.stem,
            "duration_90k": int(playlist.duration_90k),
            "score": playlist.score,
            "confidence": playlist.confidence.value,
            "warnings": list(playlist.warnings),
            "errors": list(playlist.errors),
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
                for item in playlist.play_items
            ],
            "marks": [
                {
                    "index": mark.index,
                    "play_item_index": mark.play_item_index,
                    "time_90k": int(mark.time_90k) if mark.time_90k is not None else None,
                }
                for mark in playlist.marks
            ],
            "timeline_fingerprint": [
                list(item) for item in playlist.timeline_fingerprint
            ],
        }
        try:
            qt_atomic_project_writer(
                Path(chosen),
                (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
        except OSError as error:
            self._record_error(str(error))

    @Slot(int, int)
    def show_playlist_details(self, row: int, _column: int) -> None:
        playlist = self._playlist_at_row(row)
        if playlist is not None:
            self._show_playlist_details(playlist)

    def _playlist_at_row(self, row: int) -> PlaylistInfo | None:
        if self.scan_result is None or row < 0:
            return None
        item = self.playlist_table.item(row, 0)
        stem = item.text() if item is not None else ""
        return next(
            (playlist for playlist in self.scan_result.playlists if playlist.stem == stem),
            None,
        )

    def _show_playlist_details(self, playlist: PlaylistInfo) -> None:
        details = build_playlist_structure(playlist)
        self._show_details(
            self.translations.text("playlist.details_title", stem=playlist.stem),
            format_playlist_details(details, self.translations.text),
        )

    @Slot(QPoint)
    def show_subtitle_context_menu(self, position: QPoint) -> None:
        row = self.mapping_table.rowAt(position.y())
        if self._subtitle_asset_at_row(row) is None:
            return
        menu = QMenu(self)
        details_action = menu.addAction(self.translations.text("subtitles.details"))
        if menu.exec(self.mapping_table.viewport().mapToGlobal(position)) is details_action:
            self.show_subtitle_details(row, 0)

    @Slot(int, int)
    def show_subtitle_details(self, row: int, _column: int) -> None:
        result = self.subtitle_result
        if result is None:
            return
        asset = self._subtitle_asset_at_row(row)
        if asset is None:
            return
        warnings = [
            self._subtitle_issue_text(issue)
            for issue in result.issues
            if issue.severity is ApplicationSeverity.WARNING
            and issue.source == str(asset.path)
        ]
        details = build_subtitle_details(asset, warnings=tuple(warnings))
        self._show_details(
            self.translations.text("subtitles.details_title", filename=asset.path.name),
            format_subtitle_details(details, self.translations.text),
        )

    def _subtitle_asset_at_row(self, row: int) -> SubtitleAsset | None:
        if self.subtitle_result is None:
            return None
        path = self._row_path(row)
        return next(
            (asset for asset in self.subtitle_result.assets if asset.path == path),
            None,
        )

    def _subtitle_issue_text(self, issue: ApplicationIssue) -> str:
        key = {
            "subtitle_long_tail": "details.warning_long_tail",
            "sup_duration_estimated": "details.warning_duration_estimated",
        }.get(issue.code)
        return self.translations.text(key) if key is not None else issue.message

    def _show_details(self, title: str, text: str) -> None:
        if self.details_dialog is not None:
            self.details_dialog.close()
            self.details_dialog.deleteLater()
        self.details_dialog = ReadOnlyDetailsDialog(
            title,
            text,
            self.translations.text("common.close"),
            self,
        )
        self.details_dialog.show()
        self.details_dialog.raise_()
        self.details_dialog.activateWindow()

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

    @Slot()
    def choose_subtitle_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self.translations.text("dialog.select_subtitle_directory"),
            str(self.settings.value("recent/subtitles", "")),
        )
        if selected:
            self.add_subtitle_paths((Path(selected),))

    def add_subtitle_paths(
        self,
        paths: tuple[Path, ...],
        *,
        scan_bdmv_if_empty: bool = False,
    ) -> None:
        if self.active_task is not None:
            return
        self._sync_subtitle_order()
        request = ImportSubtitlesRequest(tuple(self.subtitle_paths), paths)
        self.pending_import_bdmv_fallback = scan_bdmv_if_empty
        self._start_task(
            lambda: self.subtitle_service.discover_and_load(request),
            self.translations.text("task.loading"),
            self._subtitle_import_finished,
            kind="subtitle_import",
        )

    def _subtitle_import_finished(self, value: object) -> None:
        result = cast(ImportSubtitlesResult, value)
        self._record_issues(result.issues)
        if result.changed and result.subtitles is not None:
            if not result.subtitles.ready:
                self.task_failed = True
                self.task_status.setText(self.translations.text("task.failed"))
                self._record_issues(result.subtitles.issues)
                self.pending_import_bdmv_fallback = False
                return
            self.pending_import_bdmv_fallback = False
            self.subtitle_paths = list(result.paths)
            self._subtitles_finished(result.subtitles)
            return
        if (
            self.pending_import_bdmv_fallback
            and not result.found_subtitles
            and result.scan_candidate is not None
            and not result.issues
        ):
            self.pending_bdmv_scan_path = result.scan_candidate
        elif self.pending_import_bdmv_fallback and not result.found_subtitles:
            self.statusBar().showMessage(
                self.translations.text("dialog.unsupported_drop"), 6000
            )
        self.pending_import_bdmv_fallback = False

    def _subtitles_finished(self, value: object) -> None:
        result = cast(LoadSubtitlesResult, value)
        self.subtitle_result = result
        self._clear_mapping_constraints()
        self.mapping_dirty = False
        loaded_paths = {asset.path for asset in result.assets}
        self.subtitle_paths = [path for path in self.subtitle_paths if path in loaded_paths]
        self.subtitle_offsets_90k = {
            path: value
            for path, value in self.subtitle_offsets_90k.items()
            if path in loaded_paths
        }
        self._populate_mapping_table()
        self._invalidate_preflight(preserve_mapping=False)
        self._record_issues(result.issues)
        if self.subtitle_paths:
            self.settings.setValue("recent/subtitles", str(self.subtitle_paths[0].parent))
        self.statusBar().showMessage(
            self.translations.text("status.subtitle_complete", count=len(result.assets)), 6000
        )
        self.refresh_output_path()
        self._populate_output_targets()
        self._update_actions()

    def _populate_mapping_table(self) -> None:
        self.mapping_table.setRowCount(0)
        if self.subtitle_result is None:
            return
        for index, asset in enumerate(self.subtitle_result.assets):
            row = self.mapping_table.rowCount()
            self.mapping_table.insertRow(row)
            duration = asset.analysis.effective_end_ticks or 0
            offset_ms = self.subtitle_offsets_90k.get(asset.path, 0) // 90
            values = (
                str(index + 1),
                asset.path.name,
                asset.format.value,
                format_ticks(duration),
                "",
                "",
                "",
                f"{offset_ms} ms",
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
            self.subtitle_offsets_90k.clear()
            self._clear_mapping_constraints()
            self.mapping_dirty = False
            self._invalidate_preflight(preserve_mapping=False)
            self._populate_output_targets()

    def _reload_subtitles(self) -> None:
        if self.active_task is not None or not self.subtitle_paths:
            return
        request = LoadSubtitlesRequest(tuple(SubtitleInput(path) for path in self.subtitle_paths))
        self._start_task(
            lambda: self.subtitle_service.load_ordered(request),
            self.translations.text("task.loading"),
            self._subtitles_finished,
        )

    @Slot()
    def restore_natural_subtitle_order(self) -> None:
        self._sync_subtitle_order()
        ordered = sorted(
            self.subtitle_paths,
            key=lambda path: (natural_path_key(path), str(path)),
        )
        self._apply_subtitle_order(ordered)

    def move_selected_subtitles(self, direction: int) -> None:
        if direction not in {-1, 1}:
            raise ValueError("subtitle move direction must be -1 or 1")
        self._sync_subtitle_order()
        selected = {
            item.row() for item in self.mapping_table.selectedItems()
        }
        ordered = list(self.subtitle_paths)
        scan = range(1, len(ordered)) if direction < 0 else range(len(ordered) - 2, -1, -1)
        for row in scan:
            neighbor = row + direction
            if row in selected and neighbor not in selected:
                ordered[row], ordered[neighbor] = ordered[neighbor], ordered[row]
                selected.remove(row)
                selected.add(neighbor)
        self._apply_subtitle_order(ordered, selected_rows=selected)

    def _apply_subtitle_order(
        self,
        ordered: list[Path],
        *,
        selected_rows: set[int] | None = None,
    ) -> None:
        if ordered == self.subtitle_paths or self.active_task is not None:
            return
        current_path = self._row_path(self.mapping_table.currentRow())
        result = self.subtitle_result
        if result is not None:
            assets_by_path = {asset.path: asset for asset in result.assets}
            ordered_assets = tuple(
                assets_by_path[path] for path in ordered if path in assets_by_path
            )
            if len(ordered_assets) == len(result.assets):
                self.subtitle_paths = ordered
                self.subtitle_result = replace(result, assets=ordered_assets)
                self._clear_mapping_constraints()
                self.subtitle_offsets_90k.clear()
                self.mapping_dirty = True
                self._populate_mapping_table()
                restored_rows = selected_rows or set()
                current_row = (
                    ordered.index(current_path)
                    if current_path is not None and current_path in ordered
                    else None
                )
                self._select_subtitle_rows(
                    restored_rows,
                    current_row=(
                        current_row if current_row in restored_rows else None
                    ),
                )
                self._invalidate_preflight()
                return
        self.subtitle_paths = ordered
        self._clear_mapping_constraints()
        self.subtitle_offsets_90k.clear()
        self.mapping_dirty = True
        self._reload_subtitles()

    def _clear_mapping_constraints(self) -> None:
        self.mapping_preflight_timer.stop()
        self.pending_preflight = False
        self.locked_subtitles.clear()
        self.restored_mapping_locks = ()
        self.restored_mapping_snapshots = ()
        self.prepared = None

    def _select_subtitle_rows(
        self,
        rows: set[int],
        *,
        current_row: int | None = None,
    ) -> None:
        selection = self.mapping_table.selectionModel()
        self.mapping_table.blockSignals(True)
        try:
            self.mapping_table.clearSelection()
            for row in sorted(rows):
                if 0 <= row < self.mapping_table.rowCount():
                    selection.select(
                        self.mapping_table.model().index(row, 0),
                        QItemSelectionModel.SelectionFlag.Select
                        | QItemSelectionModel.SelectionFlag.Rows,
                    )
            if current_row is not None and current_row in rows:
                selection.setCurrentIndex(
                    self.mapping_table.model().index(current_row, 0),
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )
        finally:
            self.mapping_table.blockSignals(False)
        self.select_timeline_episode_from_table()

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
            if ordered_paths != self.subtitle_paths:
                selected_paths = {
                    path
                    for row in self.mapping_table.selectionModel().selectedRows(0)
                    if (path := self._row_path(row.row())) is not None
                }
                selected_rows = {
                    index
                    for index, path in enumerate(ordered_paths)
                    if path in selected_paths
                }
                self._apply_subtitle_order(
                    ordered_paths,
                    selected_rows=selected_rows,
                )

    @Slot(object, int)
    def _mapping_table_rows_reordered(
        self,
        source_rows: object,
        insert_at: int,
    ) -> None:
        if not isinstance(source_rows, tuple):
            return
        rows = tuple(
            sorted({row for row in source_rows if isinstance(row, int)})
        )
        if (
            self.active_task is not None
            or len(rows) != len(source_rows)
            or not rows
            or not 0 <= insert_at <= len(self.subtitle_paths)
            or any(not 0 <= row < len(self.subtitle_paths) for row in rows)
        ):
            return

        original = list(self.subtitle_paths)
        moved = [original[row] for row in rows]
        remaining = [
            path for row, path in enumerate(original) if row not in set(rows)
        ]
        adjusted_insert_at = insert_at - sum(row < insert_at for row in rows)
        adjusted_insert_at = max(0, min(adjusted_insert_at, len(remaining)))
        ordered = [
            *remaining[:adjusted_insert_at],
            *moved,
            *remaining[adjusted_insert_at:],
        ]
        if ordered == original:
            return
        selected_rows = {
            *range(adjusted_insert_at, adjusted_insert_at + len(moved))
        }
        self._apply_subtitle_order(ordered, selected_rows=selected_rows)
        self._schedule_mapping_preflight()

    @Slot()
    def apply_batch_offset(self) -> None:
        value_ms = self.offset_spin.value()
        value_90k = value_ms * 90
        rows = {item.row() for item in self.mapping_table.selectedItems()}
        for row in rows:
            path = self._row_path(row)
            item = self.mapping_table.item(row, 7)
            if path is not None and item is not None:
                self.subtitle_offsets_90k[path] = value_90k
                item.setText(f"{value_ms} ms")
                if value_90k != 0:
                    self.locked_subtitles.add(path)
                    status = self.mapping_table.item(row, 9)
                    if status is not None:
                        status.setText(self.translations.text("mapping.locked"))
        if rows:
            self.mapping_dirty = True
            self._invalidate_preflight()
            self._schedule_mapping_preflight()

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
                    self.subtitle_offsets_90k[path] = 0
                    offset_item = self.mapping_table.item(row, 7)
                    if offset_item is not None:
                        offset_item.setText("0 ms")
                    episode_id = self._episode_id_for_row(row)
                    self.restored_mapping_locks = tuple(
                        item
                        for item in self.restored_mapping_locks
                        if item.episode_id != episode_id
                    )
                status.setText(
                    self.translations.text("mapping.locked" if locked else "mapping.pending")
                )
        if rows:
            self.mapping_dirty = True
            self._invalidate_preflight()
            self._schedule_mapping_preflight()

    @Slot()
    def reset_automatic_mapping(self) -> None:
        if self.active_task is not None:
            return
        self.mapping_preflight_timer.stop()
        self.locked_subtitles.clear()
        self.subtitle_offsets_90k.clear()
        self.restored_mapping_locks = ()
        self.restored_mapping_snapshots = ()
        self.timeline.set_user_boundaries(())
        self.mapping_dirty = True
        self._invalidate_preflight(preserve_mapping=False)
        self._populate_mapping_table()
        self._schedule_mapping_preflight()

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
    def choose_report(self) -> None:
        report_format = MergeReportFormat(
            str(self.report_format.currentData() or MergeReportFormat.JSON.value)
        )
        selected, _ = QFileDialog.getSaveFileName(
            self,
            self.translations.text("dialog.select_report"),
            self.report_path.text(),
            (
                "JSON (*.json)"
                if report_format is MergeReportFormat.JSON
                else "Text (*.txt)"
            ),
        )
        if selected:
            self.report_path.setText(selected)

    @Slot()
    def _report_configuration_changed(self) -> None:
        self._update_report_controls()
        current_path = (
            Path(self.report_path.text()) if self.report_path.text().strip() else None
        )
        if self.report_enabled.isChecked() and (
            current_path is None or current_path == self.default_report_path
        ):
            extension = MergeReportFormat(
                str(self.report_format.currentData() or MergeReportFormat.JSON.value)
            ).extension
            base = (
                Path(self.output_path.text()).parent
                if self.output_path.text().strip()
                else Path.cwd()
            )
            self.default_report_path = base / f"merge-report.{extension}"
            self.report_path.setText(str(self.default_report_path))
        self._invalidate_preflight()

    def _update_report_controls(self) -> None:
        enabled = self.active_task is None and self.report_enabled.isChecked()
        for widget in (
            self.report_format,
            self.report_path,
            self.report_browse,
            self.report_collision_policy,
        ):
            widget.setEnabled(enabled)

    def _report_target(self) -> MergeReportTarget | None:
        if not self.report_enabled.isChecked():
            return None
        path_text = self.report_path.text().strip()
        if not path_text:
            self.statusBar().showMessage(
                self.translations.text("status.no_report"), 5000
            )
            return None
        project_path = self.project_path
        protected_paths = (project_path,) if project_path is not None else ()
        return MergeReportTarget(
            Path(path_text),
            MergeReportFormat(
                str(self.report_format.currentData() or MergeReportFormat.JSON.value)
            ),
            CollisionPolicy(
                str(
                    self.report_collision_policy.currentData()
                    or CollisionPolicy.ABORT.value
                )
            ),
            protected_paths,
        )

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

    def _make_target(
        self,
        context: OutputContext,
        *,
        preview: bool = False,
        state: OutputState | None = None,
    ) -> OutputTarget | None:
        output = state or self._editor_output_state()
        policy = CollisionPolicy(output.collision_policy)
        encoding = output.encoding
        mode = output.preset
        if mode == "jriver":
            return JRiverOutputTarget(output.id, policy, encoding)
        if mode == "playlist":
            return PlaylistOutputTarget(output.id, policy, encoding)
        if mode == "disc_name":
            if state is None:
                directory_text = self.output_directory.text().strip()
                directory = Path(directory_text) if directory_text else None
            else:
                directory = (
                    output.resolved_path.parent
                    if output.resolved_path is not None
                    else None
                )
            return DiscNameOutputTarget(
                output.id,
                policy,
                encoding,
                directory,
            )
        if mode == "custom":
            if state is None:
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
            elif output.resolved_path is not None:
                directory = output.resolved_path.parent
            elif context.disc_container_path is not None:
                directory = context.disc_container_path.parent
            else:
                if not preview:
                    self.statusBar().showMessage(
                        self.translations.text("status.no_output"), 5000
                    )
                return None
            return TemplateOutputTarget(
                output.id,
                policy,
                encoding,
                directory,
                self.output_template.text().strip()
                if state is None
                else output.path_template,
            )
        if output.resolved_path is not None:
            return FullPathOutputTarget(output.id, policy, encoding, output.resolved_path)
        if not preview:
            self.statusBar().showMessage(self.translations.text("status.no_output"), 5000)
        return None

    @Slot()
    def start_preflight(self) -> None:
        if self.active_task is not None:
            self.pending_preflight = True
            return
        self.pending_preflight = False
        request = self._prepare_request()
        if request is None:
            return
        revision = self.preflight_revision
        self.active_preflight_revision = revision
        self.pending_preflight = False
        self._start_task(
            lambda: self.merge_service.prepare(request),
            self.translations.text("task.preparing"),
            lambda value: self._preflight_finished_for_revision(value, revision),
            kind="preflight",
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
            input_subtitle_paths=(
                *(asset.path for asset in subtitle_result.assets),
                *((self.project_path,) if self.project_path is not None else ()),
            ),
        )
        self._store_current_output_state()
        targets = tuple(
            target
            for state in self.output_states
            if (target := self._make_target(context, state=state)) is not None
        )
        if len(targets) != len(self.output_states):
            return None
        report_target = self._report_target()
        if self.report_enabled.isChecked() and report_target is None:
            return None
        return PrepareMergeRequest(
            layout=self.scan_result.layout,
            playlist=self.selected_playlist,
            subtitles=subtitle_result,
            output_targets=targets,
            output_context=context,
            locks=self._mapping_locks(),
            additional_boundaries=self._additional_boundaries(),
            accept_low_confidence=self.accept_low_confidence.isChecked(),
            report_target=report_target,
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
        if self.mapping_table.rowCount() == 0:
            return self.restored_mapping_locks
        restored_by_episode = {
            item.episode_id: item for item in self.restored_mapping_locks
        }
        prepared_by_episode = (
            {
                item.episode_id: item
                for item in self.prepared.mapping.mappings
            }
            if self.prepared is not None and self.prepared.mapping is not None
            else {}
        )
        snapshots_by_episode = {
            item.subtitle_id: item for item in self.restored_mapping_snapshots
        }
        locks: list[MappingLock] = []
        for row in range(self.mapping_table.rowCount()):
            episode_id = self._episode_id_for_row(row)
            path = self._row_path(row)
            if episode_id is None or path is None:
                continue
            restored = restored_by_episode.get(episode_id)
            prepared_mapping = prepared_by_episode.get(episode_id)
            snapshot = snapshots_by_episode.get(episode_id)
            if restored is not None:
                start_id = restored.start_boundary_id
                end_id = restored.end_boundary_id
                default_offset_90k = int(restored.manual_offset_90k)
            elif prepared_mapping is not None:
                start_id = prepared_mapping.start_boundary.id
                end_id = prepared_mapping.end_boundary.id
                default_offset_90k = int(prepared_mapping.manual_offset_90k)
            elif snapshot is not None:
                start_id = snapshot.start_boundary_id
                end_id = snapshot.end_boundary_id
                default_offset_90k = snapshot.manual_offset_90k
            else:
                continue
            manual_offset_90k = self.subtitle_offsets_90k.get(
                path,
                default_offset_90k,
            )
            if (
                restored is None
                and path not in self.locked_subtitles
                and manual_offset_90k == 0
            ):
                continue
            locks.append(
                MappingLock(
                    episode_id,
                    start_id,
                    end_id,
                    MediaTick90k(manual_offset_90k),
                )
            )
        return tuple(locks)

    def _capture_prepared_mapping(self) -> None:
        if self.prepared is None or self.prepared.mapping is None:
            return
        locks = self._mapping_locks()
        lock_by_episode = {item.episode_id: item for item in locks}
        boundaries = self._boundary_by_id()
        snapshots: list[MappingSnapshot] = []
        for mapping in self.prepared.mapping.mappings:
            lock = lock_by_episode.get(mapping.episode_id)
            start_id = (
                lock.start_boundary_id if lock is not None else mapping.start_boundary.id
            )
            end_id = lock.end_boundary_id if lock is not None else mapping.end_boundary.id
            start = boundaries.get(start_id, mapping.start_boundary)
            end = boundaries.get(end_id, mapping.end_boundary)
            default_offset_90k = (
                int(lock.manual_offset_90k)
                if lock is not None
                else int(mapping.manual_offset_90k)
            )
            manual_offset_90k = self.subtitle_offsets_90k.get(
                Path(mapping.subtitle_ref),
                default_offset_90k,
            )
            snapshots.append(
                MappingSnapshot(
                    mapping.episode_id,
                    start_id,
                    end_id,
                    int(start.time_90k),
                    int(end.time_90k),
                    manual_offset_90k,
                    lock is not None
                    or Path(mapping.subtitle_ref) in self.locked_subtitles,
                    mapping.confidence.value,
                    mapping.warnings,
                )
            )
        self.restored_mapping_locks = locks
        self.restored_mapping_snapshots = tuple(snapshots)

    def _available_timeline_boundaries(self) -> tuple[TimelineBoundary, ...]:
        if self.selected_playlist is None:
            return ()
        return (*build_playlist_boundaries(self.selected_playlist), *self._additional_boundaries())

    def _boundary_by_id(self) -> dict[str, TimelineBoundary]:
        return {item.id: item for item in self._available_timeline_boundaries()}

    def _mapping_for_episode(self, episode_id: str) -> tuple[str, str, int] | None:
        for lock in self.restored_mapping_locks:
            if lock.episode_id == episode_id:
                return (
                    lock.start_boundary_id,
                    lock.end_boundary_id,
                    int(lock.manual_offset_90k),
                )
        if self.prepared is not None and self.prepared.mapping is not None:
            for prepared_mapping in self.prepared.mapping.mappings:
                if prepared_mapping.episode_id == episode_id:
                    return (
                        prepared_mapping.start_boundary.id,
                        prepared_mapping.end_boundary.id,
                        int(prepared_mapping.manual_offset_90k),
                    )
        for snapshot in self.restored_mapping_snapshots:
            if snapshot.subtitle_id == episode_id:
                return (
                    snapshot.start_boundary_id,
                    snapshot.end_boundary_id,
                    snapshot.manual_offset_90k,
                )
        return None

    def _episode_id_for_row(self, row: int) -> str | None:
        path = self._row_path(row)
        if path is not None and self.prepared is not None and self.prepared.mapping is not None:
            for mapping in self.prepared.mapping.mappings:
                if Path(mapping.subtitle_ref) == path:
                    return mapping.episode_id
        if 0 <= row < self.mapping_table.rowCount():
            return f"episode-{row + 1}"
        return None

    def _row_for_episode(self, episode_id: str) -> int | None:
        for row in range(self.mapping_table.rowCount()):
            if self._episode_id_for_row(row) == episode_id:
                return row
        return None

    def _install_mapping_boundary_controls(
        self,
        row: int,
        episode_id: str,
        start_boundary_id: str,
        end_boundary_id: str,
    ) -> None:
        boundaries = self._available_timeline_boundaries()
        for column, edge, current_id in (
            (4, "start", start_boundary_id),
            (5, "end", end_boundary_id),
        ):
            combo = QComboBox(self.mapping_table)
            for item in sorted(boundaries, key=lambda value: (int(value.time_90k), value.id)):
                label = format_media_time(
                    int(item.time_90k),
                    self.timeline.time_format,
                )
                combo.addItem(
                    f"{item.id}  {label}",
                    item.id,
                )
            if combo.findData(current_id) < 0:
                combo.addItem(current_id, current_id)
            combo.setCurrentIndex(combo.findData(current_id))
            combo.currentIndexChanged.connect(
                lambda _index, eid=episode_id, changed_edge=edge, widget=combo: (
                    self._mapping_boundary_combo_changed(eid, changed_edge, widget)
                )
            )
            self.mapping_table.setCellWidget(row, column, combo)

    def _refresh_mapping_boundary_controls(self) -> None:
        for row in range(self.mapping_table.rowCount()):
            episode_id = self._episode_id_for_row(row)
            if episode_id is None:
                continue
            mapping = self._mapping_for_episode(episode_id)
            if mapping is None:
                continue
            start_id, end_id, _ = mapping
            self._install_mapping_boundary_controls(
                row,
                episode_id,
                start_id,
                end_id,
            )

    def _mapping_boundary_combo_changed(
        self,
        episode_id: str,
        edge: str,
        combo: QComboBox,
    ) -> None:
        boundary_id = combo.currentData()
        if boundary_id is None or self.active_task is not None:
            return
        self._apply_mapping_boundary(episode_id, edge, str(boundary_id))

    @Slot(str, str, int, str)
    def move_episode_boundary(
        self,
        episode_id: str,
        edge: str,
        time_90k: int,
        boundary_id: str,
    ) -> None:
        del time_90k
        self._apply_mapping_boundary(episode_id, edge, boundary_id)

    def _apply_mapping_boundary(
        self,
        episode_id: str,
        edge: str,
        boundary_id: str,
    ) -> None:
        if edge not in {"start", "end"}:
            return
        current = self._mapping_for_episode(episode_id)
        if current is None:
            return
        start_id, end_id, manual_offset_90k = current
        if edge == "start":
            start_id = boundary_id
        else:
            end_id = boundary_id
        boundaries = self._boundary_by_id()
        start = boundaries.get(start_id)
        end = boundaries.get(end_id)
        if start is None or end is None or int(end.time_90k) <= int(start.time_90k):
            self.statusBar().showMessage(
                self.translations.text("status.mapping_interval_invalid"),
                5000,
            )
            row = self._row_for_episode(episode_id)
            if row is not None:
                original_start, original_end, _ = current
                self._install_mapping_boundary_controls(
                    row,
                    episode_id,
                    original_start,
                    original_end,
                )
            return
        current_locks = list(self._mapping_locks())
        replacement = MappingLock(
            episode_id,
            start_id,
            end_id,
            MediaTick90k(manual_offset_90k),
        )
        self.restored_mapping_locks = tuple(
            replacement if item.episode_id == episode_id else item
            for item in current_locks
        )
        if not any(item.episode_id == episode_id for item in current_locks):
            self.restored_mapping_locks = (*self.restored_mapping_locks, replacement)
        row = self._row_for_episode(episode_id)
        if row is not None:
            path = self._row_path(row)
            if path is not None:
                self.locked_subtitles.add(path)
            status = self.mapping_table.item(row, 9)
            if status is not None:
                status.setText(self.translations.text("mapping.locked"))
        self.mapping_dirty = True
        self._invalidate_preflight()
        self._schedule_mapping_preflight()

    def _schedule_mapping_preflight(self) -> None:
        self.pending_preflight = True
        if self.active_task is None:
            self.mapping_preflight_timer.start(0)

    @Slot()
    def select_timeline_episode_from_table(self) -> None:
        rows = self.mapping_table.selectionModel().selectedRows(0)
        selected_rows = {index.row() for index in rows}
        current_row = self.mapping_table.currentRow()
        selected_row = (
            current_row
            if current_row in selected_rows
            else rows[0].row() if rows else None
        )
        episode_id = (
            self._episode_id_for_row(selected_row)
            if selected_row is not None
            else None
        )
        self.timeline.set_selected_episode(episode_id)

    @Slot(str)
    def select_mapping_row_from_timeline(self, episode_id: str) -> None:
        row = self._row_for_episode(episode_id)
        if row is None:
            return
        self.mapping_table.blockSignals(True)
        try:
            self.mapping_table.clearSelection()
            self.mapping_table.selectRow(row)
        finally:
            self.mapping_table.blockSignals(False)
        self.timeline.set_selected_episode(episode_id)

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
        for episode_id in invalid_subtitles:
            row = self._row_for_episode(episode_id)
            path = self._row_path(row) if row is not None else None
            if path is not None:
                self.locked_subtitles.discard(path)
                self.subtitle_offsets_90k.pop(path, None)
        self.mapping_dirty = True
        self._invalidate_preflight(preserve_mapping=False)
        self._schedule_mapping_preflight()

    @Slot(str)
    def _user_boundary_deleted(self, boundary_id: str) -> None:
        prepared_mappings = (
            self.prepared.mapping.mappings
            if self.prepared is not None and self.prepared.mapping is not None
            else ()
        )
        current_locks = self._mapping_locks()
        removed_subtitles = {
            mapping.subtitle_id
            for mapping in self.restored_mapping_snapshots
            if boundary_id in {mapping.start_boundary_id, mapping.end_boundary_id}
        }
        removed_subtitles.update(
            mapping.episode_id
            for mapping in prepared_mappings
            if boundary_id in {
                mapping.start_boundary.id,
                mapping.end_boundary.id,
            }
        )
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
        for episode_id in removed_subtitles:
            row = self._row_for_episode(episode_id)
            path = self._row_path(row) if row is not None else None
            if path is not None:
                self.locked_subtitles.discard(path)
                self.subtitle_offsets_90k.pop(path, None)
        self.mapping_dirty = True
        self._invalidate_preflight(preserve_mapping=False)
        self._schedule_mapping_preflight()

    def _preflight_finished_for_revision(
        self,
        value: object,
        revision: int,
    ) -> None:
        if revision != self.preflight_revision:
            self.pending_preflight = True
            return
        self._preflight_finished(value)

    def _preflight_finished(self, value: object) -> None:
        prepared = cast(PreparedMerge, value)
        self.prepared = prepared
        self.mapping_dirty = False
        lines: list[str] = []
        if self.subtitle_result is not None:
            lines.append(self.translations.text("preflight.inputs"))
            lines.extend(f"- {asset.path}" for asset in self.subtitle_result.assets)
        if prepared.output_preflight is not None:
            lines.append(self.translations.text("preflight.outputs"))
            lines.extend(
                f"- {output.target_id}: {output.path}"
                for output in prepared.output_preflight.outputs
            )
        if prepared.report_preflight is not None:
            lines.append(self.translations.text("preflight.report"))
            lines.extend(
                f"- {output.path}" for output in prepared.report_preflight.outputs
            )
        if prepared.report is not None:
            warning_count = sum(
                issue.severity is ApplicationSeverity.WARNING
                for issue in prepared.issues
            )
            lines.extend(
                (
                    self.translations.text("preflight.summary"),
                    self.translations.text(
                        "preflight.expected_events",
                        count=prepared.report.output_event_count,
                    ),
                    self.translations.text(
                        "preflight.expected_styles",
                        count=prepared.report.output_style_count,
                    ),
                    self.translations.text(
                        "preflight.warning_count",
                        count=warning_count,
                    ),
                )
            )
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
            self.subtitle_offsets_90k[path] = int(mapping.manual_offset_90k)
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
            self._install_mapping_boundary_controls(
                row,
                mapping.episode_id,
                mapping.start_boundary.id,
                mapping.end_boundary.id,
            )
        self._show_timeline()

    @Slot()
    def start_generate(self) -> None:
        if self.mapping_dirty or self.prepared is None or not self.prepared.ready:
            self.start_preflight()
            return
        warnings = tuple(
            issue
            for issue in self.prepared.issues
            if issue.severity is ApplicationSeverity.WARNING
        )
        if warnings and not self._confirm_preflight_warnings(warnings):
            return
        request = ExecuteMergeRequest(self.prepared, accept_warnings=bool(warnings))
        self._start_task(
            lambda: self.merge_service.execute(request),
            self.translations.text("task.writing"),
            self._generate_finished,
        )

    def _confirm_preflight_warnings(
        self,
        warnings: tuple[ApplicationIssue, ...],
    ) -> bool:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(self.translations.text("confirm.warnings.title"))
        dialog.setText(
            self.translations.text("confirm.warnings.message", count=len(warnings))
        )
        dialog.setInformativeText("\n".join(f"- {issue.message}" for issue in warnings))
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        yes_button = dialog.button(QMessageBox.StandardButton.Yes)
        no_button = dialog.button(QMessageBox.StandardButton.No)
        if yes_button is not None:
            yes_button.setText(self.translations.text("common.yes"))
        if no_button is not None:
            no_button.setText(self.translations.text("common.no"))
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.setEscapeButton(QMessageBox.StandardButton.No)
        return dialog.exec() == QMessageBox.StandardButton.Yes.value

    def _generate_finished(self, value: object) -> None:
        result = cast(ExecuteMergeResult, value)
        self._record_issues(result.issues)
        if not result.succeeded:
            self.task_failed = True
            self.task_status.setText(self.translations.text("task.failed"))
            return
        count = len(result.receipt.paths) if result.receipt is not None else 0
        self.statusBar().showMessage(self.translations.text("status.written", count=count), 8000)

    def _start_task(
        self,
        operation: Callable[[], object],
        status: str,
        success: Callable[[object], None],
        *,
        kind: str = "",
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
        self.active_task_kind = kind
        self.task_failed = False
        self.task_cancelled = False
        self.task_status.setText(status)
        self.task_detail.clear()
        self.task_detail.setToolTip("")
        self.progress.setValue(0)
        self.cancel_button.setEnabled(True)
        self._update_actions()
        self.thread_pool.start(task)

    @Slot(int, str)
    def _task_progress(self, value: int, detail: str) -> None:
        self.progress.setValue(value)
        self.progress.setFormat("%p%")
        if detail == "complete":
            self.task_detail.clear()
            self.task_detail.setToolTip("")
        elif detail != "started":
            self.task_detail.setText(Path(detail).name or detail)
            self.task_detail.setToolTip(detail)

    @Slot(str, str)
    def _task_failed(self, message: str, details: str) -> None:
        self.task_failed = True
        self.pending_import_bdmv_fallback = False
        self.pending_bdmv_scan_path = None
        self.task_status.setText(self.translations.text("task.failed"))
        self._clear_failed_project_restore()
        self._record_error(f"{message}\n{details}")

    @Slot()
    def _task_cancelled(self) -> None:
        self.task_cancelled = True
        self.pending_import_bdmv_fallback = False
        self.pending_bdmv_scan_path = None
        self._clear_failed_project_restore()
        self.task_status.setText(self.translations.text("task.cancelled"))

    def _clear_failed_project_restore(self) -> None:
        if self.active_task_kind in {"project_scan", "project_subtitles"}:
            if self.active_task_kind == "project_scan":
                self.path_edit.setText(self.pending_project_previous_bdmv)
            self._discard_pending_project_restore()
            self.pending_preflight = False
            self.mapping_preflight_timer.stop()

    def _discard_pending_project_restore(self) -> None:
        self.pending_project = None
        self.pending_project_path = None
        self.pending_project_previous_bdmv = ""
        self.pending_restore_after_scan = False

    @Slot()
    def _task_finished(self) -> None:
        was_cancelled = self.cancellation is not None and self.cancellation.cancelled
        finished_kind = self.active_task_kind
        self.active_task = None
        self.active_preflight_revision = None
        self.cancellation = None
        self.cancel_button.setEnabled(False)
        self.progress.setValue(100)
        task_succeeded = (
            not was_cancelled
            and not self.task_cancelled
            and not self.task_failed
        )
        self.active_task_kind = ""
        if task_succeeded:
            self.task_status.setText(self.translations.text("task.complete"))
        self._update_actions()
        if task_succeeded and self.pending_restore_after_scan:
            self.pending_restore_after_scan = False
            self._continue_project_restore()
        elif task_succeeded and self.pending_bdmv_scan_path is not None:
            bdmv_path = self.pending_bdmv_scan_path
            self.pending_bdmv_scan_path = None
            self.path_edit.setText(str(bdmv_path))
            self.start_scan()
        elif self.pending_preflight and (
            task_succeeded or finished_kind == "preflight"
        ):
            self.mapping_preflight_timer.start(0)

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
        self.timeline.set_candidate_boundaries(self._available_timeline_boundaries())
        self.timeline.show_playlist(
            self.selected_playlist,
            item_label=self.translations.text("timeline.item"),
            chapter_label=self.translations.text("timeline.chapter"),
            empty_text=self.translations.text("timeline.empty"),
        )
        rows = self.mapping_table.selectionModel().selectedRows(0)
        selected_episode_id = (
            self._episode_id_for_row(rows[0].row()) if rows else None
        )
        self.timeline.set_episodes(
            self._timeline_episodes(),
            selected_episode_id=selected_episode_id,
        )
        self.timeline.setToolTip(self.translations.text("timeline.boundary_add"))

    def _timeline_episodes(self) -> tuple[TimelineEpisode, ...]:
        subtitle_result = self.subtitle_result
        if subtitle_result is None:
            return ()
        assets_by_path = {asset.path: asset for asset in subtitle_result.assets}
        episodes: list[TimelineEpisode] = []
        if self.prepared is not None and self.prepared.mapping is not None:
            for prepared_mapping in self.prepared.mapping.mappings:
                path = Path(prepared_mapping.subtitle_ref)
                asset = assets_by_path.get(path)
                episodes.append(
                    self._timeline_episode(
                        episode_id=prepared_mapping.episode_id,
                        label=path.name,
                        start_90k=int(prepared_mapping.start_boundary.time_90k),
                        end_90k=int(prepared_mapping.end_boundary.time_90k),
                        final_offset_90k=int(prepared_mapping.final_offset_90k),
                        earliest_start_90k=(
                            asset.analysis.earliest_start_ticks
                            if asset is not None
                            else None
                        ),
                        raw_end_90k=(
                            asset.analysis.raw_end_ticks if asset is not None else None
                        ),
                        confidence=prepared_mapping.confidence.value,
                        locked=(
                            prepared_mapping.locked
                            or path in self.locked_subtitles
                        ),
                        warnings=prepared_mapping.warnings,
                    )
                )
            return tuple(episodes)
        assets_by_episode = {
            f"episode-{index + 1}": asset
            for index, asset in enumerate(subtitle_result.assets)
        }
        for snapshot in self.restored_mapping_snapshots:
            asset = assets_by_episode.get(snapshot.subtitle_id)
            episodes.append(
                self._timeline_episode(
                    episode_id=snapshot.subtitle_id,
                    label=(
                        asset.path.name
                        if asset is not None
                        else snapshot.subtitle_id
                    ),
                    start_90k=snapshot.start_90k,
                    end_90k=snapshot.end_90k,
                    final_offset_90k=(
                        snapshot.start_90k + snapshot.manual_offset_90k
                    ),
                    earliest_start_90k=(
                        asset.analysis.earliest_start_ticks
                        if asset is not None
                        else None
                    ),
                    raw_end_90k=(
                        asset.analysis.raw_end_ticks if asset is not None else None
                    ),
                    confidence=snapshot.confidence,
                    locked=snapshot.locked,
                    warnings=snapshot.warnings,
                )
            )
        return tuple(episodes)

    @staticmethod
    def _timeline_episode(
        *,
        episode_id: str,
        label: str,
        start_90k: int,
        end_90k: int,
        final_offset_90k: int,
        earliest_start_90k: int | None,
        raw_end_90k: int | None,
        confidence: str,
        locked: bool,
        warnings: tuple[str, ...],
    ) -> TimelineEpisode:
        content_start_90k = start_90k
        content_end_90k = end_90k
        if (
            earliest_start_90k is not None
            and raw_end_90k is not None
            and raw_end_90k > earliest_start_90k
        ):
            content_start_90k = final_offset_90k + earliest_start_90k
            content_end_90k = final_offset_90k + raw_end_90k
        return TimelineEpisode(
            episode_id,
            label,
            start_90k,
            end_90k,
            content_start_90k,
            content_end_90k,
            confidence,
            locked,
            warnings,
        )

    def _invalidate_preflight(self, *, preserve_mapping: bool = True) -> None:
        if preserve_mapping:
            self._capture_prepared_mapping()
        if self.active_preflight_revision is not None:
            self.pending_preflight = True
        self.preflight_revision += 1
        self.prepared = None
        self.preflight_summary.setPlainText(self.translations.text("preflight.waiting"))
        self._show_timeline()
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
        has_subtitle_rows = idle and bool(self.subtitle_paths)
        self.scan_button.setEnabled(idle and bool(self.path_edit.text().strip()))
        self.add_subtitle_button.setEnabled(idle)
        self.add_subtitle_directory_button.setEnabled(idle)
        self.auto_map_button.setEnabled(idle and has_playlist and has_subtitles)
        self.preflight_button.setEnabled(idle and has_playlist and has_subtitles)
        self.generate_button.setEnabled(
            idle
            and not self.mapping_dirty
            and self.prepared is not None
            and self.prepared.ready
        )
        self.remove_subtitle_button.setEnabled(idle and bool(self.subtitle_paths))
        self.move_subtitle_up_button.setEnabled(has_subtitle_rows)
        self.move_subtitle_down_button.setEnabled(has_subtitle_rows)
        self.natural_sort_button.setEnabled(has_subtitle_rows)
        has_mapping = (
            self.prepared is not None and self.prepared.mapping is not None
        ) or bool(self.restored_mapping_snapshots)
        self.offset_button.setEnabled(has_subtitle_rows and has_mapping)
        self.lock_button.setEnabled(has_subtitle_rows and has_mapping)
        self.reset_mapping_button.setEnabled(has_subtitle_rows and has_playlist)
        self.path_edit.setEnabled(idle)
        self.choose_path_button.setEnabled(idle)
        self.playlist_table.setEnabled(idle)
        self.playlist_search.setEnabled(idle)
        self.primary_playlist_combo.setEnabled(idle)
        self.mapping_table.setEnabled(idle)
        self.timeline.setEnabled(idle and has_playlist)
        self.timeline_format.setEnabled(idle)
        self.output_mode.setEnabled(idle)
        self.output_directory.setEnabled(idle)
        self.output_directory_browse.setEnabled(idle)
        self.output_template.setEnabled(idle)
        self.output_path.setEnabled(idle)
        self.output_browse.setEnabled(
            idle and str(self.output_mode.currentData() or "jriver") == "full_path"
        )
        self.output_encoding.setEnabled(idle)
        self.collision_policy.setEnabled(idle)
        self.output_targets_table.setEnabled(idle)
        self.add_output_target_button.setEnabled(idle)
        self.remove_output_target_button.setEnabled(
            idle and len(self.output_states) > 1
        )
        self.report_enabled.setEnabled(idle)
        report_enabled = idle and self.report_enabled.isChecked()
        for widget in (
            self.report_format,
            self.report_path,
            self.report_browse,
            self.report_collision_policy,
        ):
            widget.setEnabled(report_enabled)
        self.accept_low_confidence.setEnabled(idle)
        self.offset_spin.setEnabled(idle)
        self.project_notes.setEnabled(idle)
        self.advanced_toggle.setEnabled(idle)
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
        if self.active_task is not None:
            event.ignore()
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()

    @override
    def dropEvent(self, event: QDropEvent) -> None:
        if self.active_task is not None:
            event.ignore()
            return
        paths = tuple(
            Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()
        )
        if paths:
            self.add_subtitle_paths(paths, scan_bdmv_if_empty=True)
            event.acceptProposedAction()
        else:
            self.statusBar().showMessage(
                self.translations.text("dialog.unsupported_drop"), 6000
            )
