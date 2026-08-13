from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, QSettings, Qt
from PySide6.QtWidgets import QComboBox, QFileDialog, QMessageBox
from pytestqt.qtbot import QtBot

from bdsubmerge.application import (
    ApplicationIssue,
    ApplicationSeverity,
    ExecuteMergeResult,
    LoadSubtitlesRequest,
    LoadSubtitlesResult,
    MergeReportFormat,
    PreparedMerge,
    ScanResult,
    SubtitleAsset,
    SubtitleInput,
)
from bdsubmerge.cancellation import CancellationCheck
from bdsubmerge.domain.models import (
    BdmvLayout,
    PlayItemInfo,
    PlaylistConfidence,
    PlaylistInfo,
    ReferenceStatus,
)
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.mapping import (
    BoundaryKind,
    EpisodeMapping,
    MappingConfidence,
    MappingLock,
    MappingResult,
)
from bdsubmerge.merge import MergeNotice, MergeReport
from bdsubmerge.output import (
    CollisionPolicy,
    OutputPreset,
    PreflightResult,
    ResolvedOutput,
    preflight_outputs,
)
from bdsubmerge.project import (
    FileFingerprint,
    MappingSnapshot,
    OutputState,
    ProjectState,
    RestoredProject,
    SourceCheck,
    SourceState,
    SubtitleState,
)
from bdsubmerge.subtitles import SubtitleFormat, TextSubtitleInfo, parse_ass
from bdsubmerge.ui.main_window import MainWindow
from bdsubmerge.ui.timeline import TimelineEpisode


def _settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _scan_result(tmp_path: Path) -> ScanResult:
    bdmv = tmp_path / "Title" / "BDMV"
    (bdmv / "PLAYLIST").mkdir(parents=True)
    (bdmv / "CLIPINF").mkdir()
    (bdmv / "STREAM").mkdir()
    (bdmv / "index.bdmv").write_bytes(b"index")
    (bdmv / "PLAYLIST" / "00001.mpls").write_bytes(b"mpls")
    layout = BdmvLayout(
        selected_path=tmp_path / "Title",
        disc_container_path=tmp_path / "Title",
        bdmv_path=bdmv,
        index_bdmv_path=bdmv / "index.bdmv",
        playlist_path=bdmv / "PLAYLIST",
        clipinf_path=bdmv / "CLIPINF",
        stream_path=bdmv / "STREAM",
    )
    playlist = PlaylistInfo(
        path=bdmv / "PLAYLIST" / "00001.mpls",
        stem="00001",
        duration_90k=MediaTick90k(24 * 60 * 90_000),
        play_items=(),
        marks=(),
        score=90,
        confidence=PlaylistConfidence.HIGH,
    )
    return ScanResult(layout, (playlist,))


def _multi_playlist_scan(tmp_path: Path, *, equivalent: bool) -> ScanResult:
    scan = _scan_result(tmp_path)
    assert scan.layout is not None
    playlists: list[PlaylistInfo] = []
    for index, stem in enumerate(("00001", "00002")):
        path = scan.layout.playlist_path / f"{stem}.mpls"
        path.write_bytes(b"mpls")
        clip_id = "00010" if equivalent or index == 0 else "00020"
        play_item = PlayItemInfo(
            index=0,
            clip_id=clip_id,
            codec_id="M2TS",
            in_time_45k=0,
            out_time_45k=45_000,
            logical_start_90k=MediaTick90k(0),
            logical_end_90k=MediaTick90k(90_000),
            connection_condition=0,
            is_multi_angle=False,
            selected_angle=0,
            angle_count=1,
            references=ReferenceStatus(True, True),
        )
        playlists.append(
            PlaylistInfo(
                path=path,
                stem=stem,
                duration_90k=MediaTick90k(90_000),
                play_items=(play_item,),
                marks=(),
                score=90 - index,
                confidence=PlaylistConfidence.HIGH,
            )
        )
    return ScanResult(scan.layout, tuple(playlists))


def _select_playlist_rows(window: MainWindow, rows: tuple[int, ...]) -> None:
    selection = window.playlist_table.selectionModel()
    window.playlist_table.blockSignals(True)
    window.playlist_table.clearSelection()
    for row in rows:
        selection.select(
            window.playlist_table.model().index(row, 0),
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows,
        )
    window.playlist_table.blockSignals(False)
    window.select_playlist()


def _prepared_mapping_window(
    qtbot: QtBot,
    tmp_path: Path,
) -> tuple[MainWindow, Path, PreparedMerge]:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    scan = _scan_result(tmp_path)
    window._scan_finished(scan)
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text("subtitle", encoding="utf-8")
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.20,0:00:01.20,Default,line\n"
    )
    asset = SubtitleAsset(
        subtitle,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 18_000, 108_000, 108_000, False),
        "utf-8",
    )
    window.subtitle_result = LoadSubtitlesResult((asset,), SubtitleFormat.ASS)
    window.subtitle_paths = [subtitle]
    window._populate_mapping_table()
    window.timeline.set_user_boundaries((("user:middle", 450_000),))
    boundaries = window._boundary_by_id()
    mapping = EpisodeMapping(
        "episode-1",
        str(subtitle),
        boundaries["playlist:start"],
        boundaries["playlist:end"],
        MediaTick90k(9_000),
        0,
        MappingConfidence.HIGH,
        warnings=("review",),
    )
    prepared = PreparedMerge(
        MappingResult((mapping,), 0, MappingConfidence.HIGH),
        None,
        None,
        None,
        (),
    )
    window._preflight_finished(prepared)
    return window, subtitle, prepared


def test_window_defaults_to_chinese_and_switches_to_english(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)

    assert window.path_label.text() == "原盘路径"

    window.set_language("en_US")

    assert window.path_label.text() == "Blu-ray path"
    assert window.settings.value("ui/language") == "en_US"


def test_scan_result_populates_playlist_and_exact_jriver_path(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    result = _scan_result(tmp_path)

    window._scan_finished(result)

    assert window.playlist_table.rowCount() == 1
    assert window.playlist_table.item(0, 0).text() == "00001"
    assert window.selected_playlist == result.playlists[0]
    assert window.output_path.text() == str(result.layout.index_bdmv_path.with_suffix(".ass"))


def test_filter_and_error_details_are_non_modal(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window._scan_finished(_scan_result(tmp_path))

    window.filter_playlists("99999")
    assert window.playlist_table.isRowHidden(0)

    window._record_issues(
        (ApplicationIssue(ApplicationSeverity.ERROR, "broken", "details"),)
    )
    qtbot.mouseClick(window.details_button, Qt.MouseButton.LeftButton)

    assert window.error_panel.isVisible() is False or "broken" in window.error_panel.toPlainText()
    assert "broken" in window.error_panel.toPlainText()


def test_generate_business_failure_remains_failed_after_task_finishes(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    prepared = PreparedMerge(None, None, None, None, ())
    issue = ApplicationIssue(ApplicationSeverity.ERROR, "output_write_failed", "denied")

    window._generate_finished(ExecuteMergeResult(prepared, False, None, (issue,)))
    window._task_finished()

    assert window.task_failed is True
    assert window.task_status.text() == window.translations.text("task.failed")
    assert "output_write_failed" in window.error_panel.toPlainText()
    assert "denied" in window.error_panel.toPlainText()


def test_preflight_displays_full_resolved_target_path(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    target = tmp_path / "Title" / "BDMV" / "index.ass"
    resolved = ResolvedOutput(
        target_id="primary",
        preset=OutputPreset.JRIVER,
        path=target,
        encoding="utf-8-sig",
        collision_policy=CollisionPolicy.ABORT,
    )
    prepared = PreparedMerge(
        mapping=None,
        output_preflight=PreflightResult((resolved,), ()),
        report=None,
        payload=None,
        issues=(),
    )

    window._preflight_finished(prepared)

    assert str(target) in window.preflight_summary.toPlainText()


def test_preflight_displays_expected_counts_and_warning_summary(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    report = MergeReport(
        ("episode",),
        4,
        3,
        notices=(MergeNotice("warning", "review", "review output"),),
        output_style_count=2,
    )
    prepared = PreparedMerge(
        mapping=None,
        output_preflight=None,
        report=report,
        payload=None,
        issues=(
            ApplicationIssue(ApplicationSeverity.WARNING, "merge_review", "review output"),
        ),
    )

    window._preflight_finished(prepared)

    summary = window.preflight_summary.toPlainText()
    assert "预计事件数：3" in summary  # noqa: RUF001
    assert "预计样式数：2" in summary  # noqa: RUF001
    assert "警告数：1" in summary  # noqa: RUF001


@pytest.mark.parametrize("confirmed", (False, True))
def test_warning_only_preflight_requires_explicit_generation_confirmation(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    confirmed: bool,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    prepared = PreparedMerge(
        MappingResult((), 0, MappingConfidence.HIGH),
        PreflightResult((), ()),
        MergeReport((), 0, 0),
        "subtitle",
        (ApplicationIssue(ApplicationSeverity.WARNING, "review", "review output"),),
    )
    started: list[object] = []
    reviewed: list[tuple[ApplicationIssue, ...]] = []
    window.prepared = prepared
    window.mapping_dirty = False

    def confirm(warnings: tuple[ApplicationIssue, ...]) -> bool:
        reviewed.append(warnings)
        return confirmed

    monkeypatch.setattr(window, "_confirm_preflight_warnings", confirm)
    monkeypatch.setattr(window, "_start_task", lambda *args, **kwargs: started.append(args))

    window.start_generate()

    assert reviewed == [prepared.issues]
    assert bool(started) is confirmed


def test_info_only_preflight_generates_without_confirmation(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window.prepared = PreparedMerge(
        MappingResult((), 0, MappingConfidence.HIGH),
        PreflightResult((), ()),
        MergeReport((), 0, 0),
        "subtitle",
        (ApplicationIssue(ApplicationSeverity.INFO, "note", "details"),),
    )
    window.mapping_dirty = False
    started: list[object] = []
    monkeypatch.setattr(
        window,
        "_confirm_preflight_warnings",
        lambda _warnings: pytest.fail("information must not require confirmation"),
    )
    monkeypatch.setattr(window, "_start_task", lambda *args, **kwargs: started.append(args))

    window.start_generate()

    assert started


def test_error_preflight_never_starts_generation(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window.prepared = PreparedMerge(
        MappingResult((), 0, MappingConfidence.HIGH),
        PreflightResult((), ()),
        MergeReport((), 0, 0),
        "subtitle",
        (ApplicationIssue(ApplicationSeverity.ERROR, "blocked", "details"),),
    )
    window.mapping_dirty = False
    preflight_started: list[bool] = []
    generation_started: list[object] = []
    monkeypatch.setattr(window, "start_preflight", lambda: preflight_started.append(True))
    monkeypatch.setattr(
        window,
        "_start_task",
        lambda *args, **kwargs: generation_started.append(args),
    )

    window.start_generate()

    assert preflight_started == [True]
    assert generation_started == []


def test_warning_confirmation_is_localized_and_defaults_to_no(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    observed: list[QMessageBox] = []

    def reject(dialog: QMessageBox) -> int:
        observed.append(dialog)
        return QMessageBox.StandardButton.No.value

    monkeypatch.setattr(QMessageBox, "exec", reject)

    confirmed = window._confirm_preflight_warnings(
        (ApplicationIssue(ApplicationSeverity.WARNING, "review", "review output"),)
    )

    assert confirmed is False
    assert len(observed) == 1
    dialog = observed[0]
    assert dialog.windowTitle() == "确认警告"
    assert dialog.text() == "预检包含 1 条警告。仍要生成字幕吗？"  # noqa: RUF001
    assert dialog.informativeText() == "- review output"
    assert dialog.standardButton(dialog.defaultButton()) == QMessageBox.StandardButton.No
    assert dialog.standardButton(dialog.escapeButton()) == QMessageBox.StandardButton.No
    assert dialog.button(QMessageBox.StandardButton.Yes).text() == "是"
    assert dialog.button(QMessageBox.StandardButton.No).text() == "否"


def test_playlist_double_click_opens_localized_read_only_structure(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window._scan_finished(_scan_result(tmp_path))

    window.playlist_table.cellDoubleClicked.emit(0, 0)

    dialog = window.details_dialog
    assert dialog is not None
    assert dialog.isVisible()
    assert dialog.windowTitle() == "播放列表 00001 结构"
    assert "PlayItem（0）" in dialog.details.toPlainText()  # noqa: RUF001
    assert dialog.details.isReadOnly()


def test_subtitle_double_click_shows_loaded_source_analysis(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window, subtitle, _prepared = _prepared_mapping_window(qtbot, tmp_path)
    assert window.subtitle_result is not None
    window.subtitle_result = replace(
        window.subtitle_result,
        issues=(
            ApplicationIssue(
                ApplicationSeverity.WARNING,
                "subtitle_long_tail",
                "effective duration excludes a suspected long-tail event",
                str(subtitle),
            ),
        ),
    )

    window.mapping_table.cellDoubleClicked.emit(0, 1)

    dialog = window.details_dialog
    assert dialog is not None
    assert dialog.isVisible()
    assert subtitle.name in dialog.windowTitle()
    details = dialog.details.toPlainText()
    assert "事件数: 1" in details
    assert "样式数: 1" in details
    assert "文件名: episode.ass" in details
    assert "警告（1）" in details  # noqa: RUF001
    assert "已排除疑似超长尾事件计算有效时长" in details
    assert str(subtitle) in details


def test_output_target_table_shows_complete_localized_summary(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    subtitle = tmp_path / "episode.ass"
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
    )
    asset = SubtitleAsset(
        subtitle,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
        "utf-8",
    )
    target = tmp_path / "merged.ass"
    window.subtitle_result = LoadSubtitlesResult((asset,), SubtitleFormat.ASS)
    window.output_states = [
        OutputState(
            "primary",
            "full_path",
            "",
            target,
            "utf-8-sig",
            CollisionPolicy.BACKUP.value,
            "backup",
        )
    ]

    window._populate_output_targets()

    assert window.output_targets_table.columnCount() == 7
    assert tuple(
        window.output_targets_table.horizontalHeaderItem(column).text()
        for column in range(7)
    ) == (
        "目标 ID",
        "输出模式",
        "完整目标路径",
        "输出格式",
        "编码",
        "冲突策略",
        "备份",
    )
    assert tuple(
        window.output_targets_table.item(0, column).text()
        for column in range(7)
    ) == (
        "primary",
        "完整文件路径",
        str(target),
        "ass",
        "utf-8-sig",
        "覆盖前备份",
        "是",
    )


def test_loading_subtitles_refreshes_output_format_summary(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    assert window.output_targets_table.item(0, 3).text() == "未知"
    subtitle = tmp_path / "episode.ass"
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
    )
    asset = SubtitleAsset(
        subtitle,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
        "utf-8",
    )

    window._subtitles_finished(LoadSubtitlesResult((asset,), SubtitleFormat.ASS))

    assert window.output_targets_table.item(0, 3).text() == "ass"


def test_ac08_low_confidence_is_visible_and_requires_confirmation(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window._scan_finished(_scan_result(tmp_path))
    subtitle = tmp_path / "short.ass"
    subtitle.write_text("subtitle", encoding="utf-8")
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:10.00,Default,line\n"
    )
    asset = SubtitleAsset(
        subtitle,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 0, 900_000, 900_000, False),
        "utf-8",
    )
    window.subtitle_result = LoadSubtitlesResult((asset,), SubtitleFormat.ASS)
    window.subtitle_paths = [subtitle]
    window._populate_mapping_table()

    blocked_request = window._prepare_request()
    assert blocked_request is not None
    blocked = window.merge_service.prepare(blocked_request)
    window._preflight_finished(blocked)

    assert blocked.ready is False
    assert "low_mapping_confidence" in window.preflight_summary.toPlainText()
    assert window.generate_button.isEnabled() is False

    window.accept_low_confidence.setChecked(True)
    accepted_request = window._prepare_request()
    assert accepted_request is not None
    accepted = window.merge_service.prepare(accepted_request)
    window._preflight_finished(accepted)

    assert accepted.ready is True
    assert window.generate_button.isEnabled() is True


def test_geometry_and_preferences_are_persisted(qtbot: QtBot, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.resize(1100, 760)
    window.set_language("en_US")

    window.close()
    settings.sync()

    assert settings.value("ui/geometry") is not None
    assert settings.value("ui/language") == "en_US"


def test_project_state_captures_subtitles_mapping_output_and_notes(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    scan = _scan_result(tmp_path)
    window._scan_finished(scan)
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text("subtitle", encoding="utf-8")
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
    )
    asset = SubtitleAsset(
        subtitle,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
        "utf-8",
    )
    window.subtitle_result = LoadSubtitlesResult((asset,), SubtitleFormat.ASS)
    window.subtitle_paths = [subtitle]
    window._populate_mapping_table()
    window.project_notes.setText("note")

    state = window._project_state()

    assert state.subtitles[0].path == subtitle
    assert state.outputs[0].resolved_path == Path(window.output_path.text())
    assert state.ui_notes == "note"
    assert {boundary.id for boundary in state.boundaries} == {"playlist:start", "playlist:end"}


def test_project_state_captures_and_restores_multiple_output_targets(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window._scan_finished(_scan_result(tmp_path))
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text("subtitle", encoding="utf-8")
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
    )
    asset = SubtitleAsset(
        subtitle,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
        "utf-8",
    )
    window.subtitle_result = LoadSubtitlesResult((asset,), SubtitleFormat.ASS)
    window.subtitle_paths = [subtitle]
    second_path = tmp_path / "exports" / "merged.ass"

    window.add_output_target()
    window.output_path.setText(str(second_path))

    state = window._project_state()
    assert tuple(item.id for item in state.outputs) == ("primary", "output-2")
    assert state.outputs[1].resolved_path == second_path

    restored = MainWindow(settings=_settings(tmp_path / "restored"))
    qtbot.addWidget(restored)
    restored._restore_output_states(state.outputs)

    assert restored.output_targets_table.rowCount() == 2
    assert restored.output_states == list(state.outputs)
    assert restored.editing_output_id == "primary"


def test_open_project_source_checks_are_shown_without_modal_dialog(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    fingerprint = FileFingerprint(1, 2)
    check = SourceCheck(
        "episode-1", tmp_path / "missing.ass", SourceState.MISSING, fingerprint, None
    )
    state = ProjectState(
        tmp_path / "BDMV",
        tmp_path / "BDMV" / "index.bdmv",
        tmp_path / "BDMV" / "PLAYLIST" / "00001.mpls",
        "00001",
        90_000,
        (),
        (),
        (),
        (),
        (OutputState("primary", "jriver", "", None, "utf-8", "abort"),),
    )

    window._show_source_checks(RestoredProject(state, (check,)))

    assert "missing.ass" in window.error_panel.toPlainText()


def test_failed_project_scan_preserves_previous_project_association(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    previous_project = tmp_path / "previous.bdsm.json"
    next_project = tmp_path / "next.bdsm.json"
    previous_bdmv = str(tmp_path / "Previous" / "BDMV")
    state = ProjectState(
        tmp_path / "Next" / "BDMV",
        tmp_path / "Next" / "BDMV" / "index.bdmv",
        tmp_path / "Next" / "BDMV" / "PLAYLIST" / "00001.mpls",
        "00001",
        90_000,
        (),
        (),
        (),
        (),
        (),
    )
    window.project_path = previous_project
    window.pending_project = RestoredProject(state, ())
    window.pending_project_path = next_project
    window.pending_project_previous_bdmv = previous_bdmv
    window.path_edit.setText(str(state.bdmv_path))
    failed = ScanResult(
        None,
        (),
        (ApplicationIssue(ApplicationSeverity.ERROR, "scan_failed", "boom"),),
    )

    window._scan_finished(failed)

    assert window.project_path == previous_project
    assert window.pending_project is None
    assert window.pending_project_path is None
    assert window.path_edit.text() == previous_bdmv
    assert window.task_status.text() == window.translations.text("task.failed")


def test_successful_project_scan_clears_old_association_until_restore_completes(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    scan = _scan_result(tmp_path)
    assert scan.layout is not None
    previous_project = tmp_path / "previous.bdsm.json"
    next_project = tmp_path / "next.bdsm.json"
    state = ProjectState(
        scan.layout.bdmv_path,
        scan.layout.index_bdmv_path,
        scan.playlists[0].path,
        scan.playlists[0].stem,
        int(scan.playlists[0].duration_90k),
        (),
        (),
        (),
        (),
        (),
    )
    window.project_path = previous_project
    window.pending_project = RestoredProject(state, ())
    window.pending_project_path = next_project

    window._scan_finished(scan)

    assert window.project_path is None
    assert window.pending_project_path == next_project
    assert window.pending_restore_after_scan is True


def test_manual_scan_of_another_bdmv_clears_project_association(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    previous_scan = _scan_result(tmp_path / "previous")
    next_scan = _scan_result(tmp_path / "next")
    window._scan_finished(previous_scan)
    window.project_path = tmp_path / "previous.bdsm.json"

    window._scan_finished(next_scan)

    assert window.project_path is None


def test_failed_project_subtitle_restore_keeps_new_workspace_unassociated(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    scan = _scan_result(tmp_path)
    window._scan_finished(scan)
    subtitle = tmp_path / "broken.ass"
    state = ProjectState(
        scan.layout.bdmv_path,
        scan.layout.index_bdmv_path,
        scan.playlists[0].path,
        scan.playlists[0].stem,
        int(scan.playlists[0].duration_90k),
        (),
        (SubtitleState("episode-1", subtitle, "ass", "utf-8", 0),),
        (),
        (),
        (),
    )
    window.project_path = None
    window.pending_project = RestoredProject(state, ())
    window.pending_project_path = tmp_path / "next.bdsm.json"
    failed = LoadSubtitlesResult(
        (),
        None,
        (ApplicationIssue(ApplicationSeverity.ERROR, "subtitle_load_failed", "boom"),),
    )

    window._project_subtitles_finished(failed)

    assert window.project_path is None
    assert window.pending_project is None
    assert window.pending_project_path is None

    subtitle.write_text(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n",
        encoding="utf-8",
    )
    document = parse_ass(subtitle.read_text(encoding="utf-8"))
    asset = SubtitleAsset(
        subtitle,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
        "utf-8",
    )
    save_as = tmp_path / "recovered.bdsm.json"
    saved_paths: list[Path] = []
    window.subtitle_result = LoadSubtitlesResult((asset,), SubtitleFormat.ASS)
    window.subtitle_paths = [subtitle]
    window.selected_playlist = scan.playlists[0]
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args: (str(save_as), "BDSubMerge (*.bdsm.json)"),
    )
    monkeypatch.setattr(
        "bdsubmerge.ui.main_window.capture_and_save",
        lambda state, path: saved_paths.append(path),
    )

    window.save_project()

    assert saved_paths == [save_as]
    assert window.project_path == save_as


def test_playlist_table_supports_multiple_selection(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)

    assert window.playlist_table.selectionMode().name == "ExtendedSelection"


def test_all_five_output_modes_are_available(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)

    modes = tuple(
        str(window.output_mode.itemData(index))
        for index in range(window.output_mode.count())
    )

    assert modes == ("jriver", "playlist", "disc_name", "custom", "full_path")


def test_multiple_targets_have_unique_ids_and_are_forwarded_to_prepare(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window._scan_finished(_scan_result(tmp_path))
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text("subtitle", encoding="utf-8")
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
    )
    asset = SubtitleAsset(
        subtitle,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
        "utf-8",
    )
    window.subtitle_result = LoadSubtitlesResult((asset,), SubtitleFormat.ASS)
    window.subtitle_paths = [subtitle]

    window.add_output_target()
    window.output_path.setText(str(tmp_path / "alternate.ass"))
    window.add_output_target()
    window.output_path.setText(str(tmp_path / "archive.ass"))

    request = window._prepare_request()

    assert request is not None
    assert tuple(target.target_id for target in request.output_targets) == (
        "primary",
        "output-2",
        "output-3",
    )
    assert len({target.target_id for target in request.output_targets}) == 3


def test_optional_report_configuration_is_forwarded_and_shown_in_preflight(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window._scan_finished(_scan_result(tmp_path))
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text("subtitle", encoding="utf-8")
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
    )
    asset = SubtitleAsset(
        subtitle,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
        "utf-8",
    )
    window.subtitle_result = LoadSubtitlesResult((asset,), SubtitleFormat.ASS)
    window.subtitle_paths = [subtitle]
    report_path = tmp_path / "reports" / "merge.txt"
    window.report_enabled.setChecked(True)
    window.report_format.setCurrentIndex(
        window.report_format.findData(MergeReportFormat.TEXT.value)
    )
    window.report_path.setText(str(report_path))
    window.report_collision_policy.setCurrentIndex(
        window.report_collision_policy.findData(CollisionPolicy.BACKUP.value)
    )

    request = window._prepare_request()

    assert request is not None
    assert request.report_target is not None
    assert request.report_target.path == report_path
    assert request.report_target.report_format is MergeReportFormat.TEXT
    assert request.report_target.collision_policy is CollisionPolicy.BACKUP

    resolved_report = ResolvedOutput(
        target_id="__bdsubmerge_merge_report__",
        preset=OutputPreset.FULL_PATH,
        path=report_path,
        encoding="utf-8",
        collision_policy=CollisionPolicy.BACKUP,
    )
    primary_output = ResolvedOutput(
        target_id="primary",
        preset=OutputPreset.JRIVER,
        path=tmp_path / "Title" / "BDMV" / "index.ass",
        encoding="utf-8-sig",
        collision_policy=CollisionPolicy.ABORT,
    )
    alternate_output = ResolvedOutput(
        target_id="output-2",
        preset=OutputPreset.FULL_PATH,
        path=tmp_path / "alternate.ass",
        encoding="utf-8-sig",
        collision_policy=CollisionPolicy.ABORT,
    )
    prepared = PreparedMerge(
        mapping=None,
        output_preflight=PreflightResult((primary_output, alternate_output), ()),
        report=None,
        payload=None,
        issues=(),
        report_preflight=PreflightResult((resolved_report,), ()),
    )
    window._preflight_finished(prepared)

    summary = window.preflight_summary.toPlainText()
    assert str(subtitle) in summary
    assert str(primary_output.path) in summary
    assert str(alternate_output.path) in summary
    assert str(report_path) in summary


def test_custom_output_exposes_directory_template_and_final_path(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window._scan_finished(_scan_result(tmp_path))
    output_directory = tmp_path / "exports"
    window.output_mode.setCurrentIndex(window.output_mode.findData("custom"))
    window.output_directory.setText(str(output_directory))
    window.output_template.setText("{disc_name}_{playlist_stem}.{format}")

    assert window.output_directory_row.isHidden() is False
    assert window.output_template.isHidden() is False
    assert window.output_path.text() == str(output_directory / "Title_00001.ass")


def test_equivalent_jriver_playlists_auto_select_primary_and_show_compatibility(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window._scan_finished(_multi_playlist_scan(tmp_path, equivalent=True))

    _select_playlist_rows(window, (0, 1))

    assert window.playlist_selection is not None
    assert window.playlist_selection.ready is True
    assert window.selected_playlist is not None
    assert window.selected_playlist.stem == "00001"
    assert window.primary_playlist_row.isHidden() is True
    assert "00001, 00002" in window.playlist_compatibility.text()


def test_non_equivalent_jriver_playlists_require_explicit_primary(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window._scan_finished(_multi_playlist_scan(tmp_path, equivalent=False))

    _select_playlist_rows(window, (0, 1))

    assert window.playlist_selection is not None
    assert window.playlist_selection.ready is False
    assert window.selected_playlist is None
    assert window.primary_playlist_row.isHidden() is False
    assert "多个不等价播放列表" in window.playlist_warning.text()
    assert "唯一选择" in window.playlist_warning.text()

    window.primary_playlist_combo.setCurrentIndex(
        window.primary_playlist_combo.findData("00002")
    )

    assert window.playlist_selection is not None
    assert window.playlist_selection.ready is True
    assert window.selected_playlist is not None
    assert window.selected_playlist.stem == "00002"
    assert "00002" in window.playlist_compatibility.text()


def test_restored_mapping_locks_are_used_before_new_preflight(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    lock = MappingLock("episode-1", "start", "end", MediaTick90k(900))
    window.restored_mapping_locks = (lock,)

    assert window._mapping_locks() == (lock,)


def test_project_mapping_is_restored_by_subtitle_id(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text("subtitle", encoding="utf-8")
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
    )
    asset = SubtitleAsset(
        subtitle,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
        "utf-8",
    )
    mapping = MappingSnapshot(
        "episode-1",
        "playlist:start",
        "playlist:end",
        0,
        90_000,
        901,
        True,
        "high",
    )
    state = ProjectState(
        tmp_path / "BDMV",
        tmp_path / "BDMV" / "index.bdmv",
        tmp_path / "BDMV" / "PLAYLIST" / "00001.mpls",
        "00001",
        90_000,
        (),
        (SubtitleState("episode-1", subtitle, "ass", "utf-8", 0),),
        (),
        (mapping,),
        (),
    )
    window.subtitle_paths = [subtitle]
    window.pending_project = RestoredProject(state, ())
    project_path = tmp_path / "restored.bdsm.json"
    window.pending_project_path = project_path

    window._project_subtitles_finished(LoadSubtitlesResult((asset,), SubtitleFormat.ASS))

    assert window.restored_mapping_locks == (
        MappingLock(
            "episode-1",
            "playlist:start",
            "playlist:end",
            MediaTick90k(901),
        ),
    )
    assert window.mapping_table.item(0, 4).text() == "playlist:start"
    assert window.mapping_table.item(0, 5).text() == "playlist:end"
    assert window.mapping_table.item(0, 7).text() == "10 ms"
    assert window.subtitle_offsets_90k[subtitle] == 901
    assert window._mapping_locks()[0].manual_offset_90k == 901
    assert window.project_path == project_path
    assert window.pending_project is None
    assert window.pending_project_path is None


def test_adding_directory_preserves_manual_order_and_appends_naturally(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    subtitle_dir = tmp_path / "Subtitles"
    subtitle_dir.mkdir()
    episode_1 = subtitle_dir / "E1.ass"
    episode_2 = subtitle_dir / "E2.ass"
    episode_10 = subtitle_dir / "E10.ass"
    for path in (episode_1, episode_2, episode_10):
        path.write_text("subtitle", encoding="utf-8")
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
    )
    assets = {
        path: SubtitleAsset(
            path,
            SubtitleFormat.ASS,
            document,
            TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
            "utf-8",
        )
        for path in (episode_1, episode_2, episode_10)
    }
    window.subtitle_result = LoadSubtitlesResult(
        (assets[episode_1], assets[episode_10]),
        SubtitleFormat.ASS,
    )
    window.subtitle_paths = [episode_1, episode_10]
    window._populate_mapping_table()
    first_path = window.mapping_table.item(0, 0).data(Qt.ItemDataRole.UserRole)
    last_path = window.mapping_table.item(1, 0).data(Qt.ItemDataRole.UserRole)
    window.mapping_table.item(0, 0).setData(Qt.ItemDataRole.UserRole, last_path)
    window.mapping_table.item(1, 0).setData(Qt.ItemDataRole.UserRole, first_path)
    requests: list[LoadSubtitlesRequest] = []

    def load_ordered(
        request: LoadSubtitlesRequest,
        *,
        cancellation_check: CancellationCheck | None = None,
    ) -> LoadSubtitlesResult:
        del cancellation_check
        requests.append(request)
        return LoadSubtitlesResult(
            tuple(assets[source.path] for source in request.sources),
            SubtitleFormat.ASS,
        )

    def run_immediately(
        operation: Callable[[], object],
        status: str,
        success: Callable[[object], None],
        *,
        kind: str = "",
    ) -> None:
        del status, kind
        success(operation())

    monkeypatch.setattr(window.subtitle_service, "load_ordered", load_ordered)
    monkeypatch.setattr(window, "_start_task", run_immediately)

    window.add_subtitle_paths((subtitle_dir,))
    window.add_subtitle_paths((subtitle_dir,))

    assert len(requests) == 1
    assert tuple(source.path for source in requests[0].sources) == (
        episode_10,
        episode_1,
        episode_2,
    )


def test_project_restore_uses_saved_subtitle_order_and_encoding(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    scan = _scan_result(tmp_path)
    window._scan_finished(scan)
    episode_1 = tmp_path / "E1.ass"
    episode_2 = tmp_path / "E2.ass"
    stale = tmp_path / "stale.ass"
    for path in (episode_1, episode_2, stale):
        path.write_text("subtitle", encoding="utf-8")
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
    )
    assets = {
        path: SubtitleAsset(
            path,
            SubtitleFormat.ASS,
            document,
            TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
            encoding,
        )
        for path, encoding in ((episode_1, "gb18030"), (episode_2, "shift_jis"))
    }
    requests: list[LoadSubtitlesRequest] = []

    def load_ordered(
        request: LoadSubtitlesRequest,
        *,
        cancellation_check: CancellationCheck | None = None,
    ) -> LoadSubtitlesResult:
        del cancellation_check
        requests.append(request)
        return LoadSubtitlesResult(
            tuple(assets[source.path] for source in request.sources),
            SubtitleFormat.ASS,
        )

    def run_immediately(
        operation: Callable[[], object],
        status: str,
        success: Callable[[object], None],
        *,
        kind: str = "",
    ) -> None:
        del status, kind
        success(operation())

    monkeypatch.setattr(window.subtitle_service, "load_ordered", load_ordered)
    monkeypatch.setattr(window, "_start_task", run_immediately)
    state = ProjectState(
        scan.layout.bdmv_path,
        scan.layout.index_bdmv_path,
        scan.playlists[0].path,
        scan.playlists[0].stem,
        int(scan.playlists[0].duration_90k),
        (),
        (
            SubtitleState("episode-2", episode_2, "ass", "shift_jis", 1),
            SubtitleState("episode-1", episode_1, "ass", "gb18030", 0),
        ),
        (),
        (),
        (),
    )
    window.subtitle_paths = [stale]
    window.locked_subtitles.add(stale)
    window.subtitle_offsets_90k[stale] = 9_000
    window.pending_project = RestoredProject(state, ())

    window._continue_project_restore()

    assert requests[0].sources == (
        SubtitleInput(episode_1, "gb18030"),
        SubtitleInput(episode_2, "shift_jis"),
    )
    assert window.subtitle_paths == [episode_1, episode_2]
    assert tuple(window._row_path(row) for row in range(2)) == (episode_1, episode_2)
    assert stale not in window.locked_subtitles
    assert stale not in window.subtitle_offsets_90k


def test_user_boundaries_are_forwarded_and_invalidate_preflight(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window._scan_finished(_scan_result(tmp_path))
    window.prepared = PreparedMerge(None, None, None, None, ())

    boundary_id = window.timeline.add_user_boundary(450_000, "user:restored")

    additional = window._additional_boundaries()
    assert boundary_id == "user:restored"
    assert len(additional) == 1
    assert additional[0].id == "user:restored"
    assert additional[0].kinds == {BoundaryKind.USER}
    assert additional[0].sources[0].reference == "ui"
    assert additional[0].user_created is True
    assert window.prepared is None
    assert window.mapping_dirty is True


def test_deleting_user_boundary_drops_its_restored_lock(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    window._scan_finished(_scan_result(tmp_path))
    lock = MappingLock(
        "episode-1",
        "playlist:start",
        "user:restored",
        MediaTick90k(0),
    )
    window.restored_mapping_locks = (lock,)
    window.timeline.set_user_boundaries((("user:restored", 450_000),))
    window.prepared = PreparedMerge(None, None, None, None, ())

    window.timeline.remove_user_boundary("user:restored")

    assert window.restored_mapping_locks == ()
    assert window.prepared is None
    assert window.mapping_dirty is True


def test_prepared_mapping_is_projected_to_timeline_episode(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    window, subtitle, _ = _prepared_mapping_window(qtbot, tmp_path)

    episodes = window._timeline_episodes()

    assert episodes == (
        TimelineEpisode(
            "episode-1",
            subtitle.name,
            0,
            129_600_000,
            27_000,
            117_000,
            "high",
            False,
            ("review",),
        ),
    )
    assert window.timeline._episodes == episodes


def test_preflight_installs_boundary_combos_in_mapping_table(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    window, _, _ = _prepared_mapping_window(qtbot, tmp_path)

    start_combo = window.mapping_table.cellWidget(0, 4)
    end_combo = window.mapping_table.cellWidget(0, 5)

    assert isinstance(start_combo, QComboBox)
    assert isinstance(end_combo, QComboBox)
    assert start_combo.currentData() == "playlist:start"
    assert end_combo.currentData() == "playlist:end"
    assert start_combo.findData("user:middle") >= 0
    assert end_combo.findData("user:middle") >= 0


def test_mapping_table_and_timeline_selection_are_bidirectional(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    window, _, _ = _prepared_mapping_window(qtbot, tmp_path)

    window.mapping_table.selectRow(0)
    window.select_timeline_episode_from_table()

    assert window.timeline._selected_episode_id == "episode-1"

    window.mapping_table.clearSelection()
    window.timeline.set_selected_episode(None)
    window.select_mapping_row_from_timeline("episode-1")

    assert tuple(
        index.row()
        for index in window.mapping_table.selectionModel().selectedRows(0)
    ) == (0,)
    assert window.timeline._selected_episode_id == "episode-1"


def test_mapping_table_reorder_updates_assets_and_invalidates_mapping(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, first_path, _ = _prepared_mapping_window(qtbot, tmp_path)
    second_path = tmp_path / "episode-2.ass"
    second_path.write_text("subtitle", encoding="utf-8")
    assert window.subtitle_result is not None
    first_asset = window.subtitle_result.assets[0]
    second_asset = replace(first_asset, path=second_path)
    window.subtitle_paths = [first_path, second_path]
    window.subtitle_result = LoadSubtitlesResult(
        (first_asset, second_asset),
        SubtitleFormat.ASS,
    )
    window._populate_mapping_table()
    window.mapping_table.selectRow(0)

    def schedule() -> None:
        window.pending_preflight = True

    monkeypatch.setattr(window, "_schedule_mapping_preflight", schedule)

    window._mapping_table_rows_reordered((0,), 2)

    assert window.subtitle_paths == [second_path, first_path]
    assert window.subtitle_result.assets == (second_asset, first_asset)
    assert window.prepared is None
    assert window.restored_mapping_locks == ()
    assert window.restored_mapping_snapshots == ()
    assert window.mapping_dirty is True
    assert window.pending_preflight is True
    assert window._row_path(1) == first_path
    assert tuple(
        index.row()
        for index in window.mapping_table.selectionModel().selectedRows(0)
    ) == (1,)


def test_mapping_table_reorder_preserves_multiple_rows_at_bottom(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, first_path, _ = _prepared_mapping_window(qtbot, tmp_path)
    assert window.subtitle_result is not None
    first_asset = window.subtitle_result.assets[0]
    paths = [
        first_path,
        *(tmp_path / f"episode-{index}.ass" for index in range(2, 5)),
    ]
    for path in paths[1:]:
        path.write_text("subtitle", encoding="utf-8")
    assets = tuple(replace(first_asset, path=path) for path in paths)
    window.subtitle_paths = paths
    window.subtitle_result = LoadSubtitlesResult(assets, SubtitleFormat.ASS)
    window._populate_mapping_table()
    monkeypatch.setattr(window, "_schedule_mapping_preflight", lambda: None)

    window._mapping_table_rows_reordered((1, 2), 4)

    expected_paths = [paths[0], paths[3], paths[1], paths[2]]
    assert window.subtitle_paths == expected_paths
    assert window.subtitle_result.assets == (
        assets[0],
        assets[3],
        assets[1],
        assets[2],
    )
    assert tuple(
        index.row()
        for index in window.mapping_table.selectionModel().selectedRows(0)
    ) == (2, 3)


def test_mapping_table_reorder_inside_selection_is_a_noop(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, first_path, prepared = _prepared_mapping_window(qtbot, tmp_path)
    second_path = tmp_path / "episode-2.ass"
    second_path.write_text("subtitle", encoding="utf-8")
    assert window.subtitle_result is not None
    first_asset = window.subtitle_result.assets[0]
    window.subtitle_paths = [first_path, second_path]
    window.subtitle_result = LoadSubtitlesResult(
        (first_asset, replace(first_asset, path=second_path)),
        SubtitleFormat.ASS,
    )
    window._populate_mapping_table()
    scheduled: list[None] = []
    monkeypatch.setattr(
        window,
        "_schedule_mapping_preflight",
        lambda: scheduled.append(None),
    )

    window._mapping_table_rows_reordered((0, 1), 1)

    assert window.subtitle_paths == [first_path, second_path]
    assert window.prepared is prepared
    assert scheduled == []


def test_offset_and_lock_controls_require_an_existing_mapping(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    window = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(window)
    subtitle = tmp_path / "episode.ass"
    subtitle.write_text("subtitle", encoding="utf-8")
    document = parse_ass(
        "[Script Info]\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
    )
    asset = SubtitleAsset(
        subtitle,
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
        "utf-8",
    )
    window.subtitle_paths = [subtitle]
    window.subtitle_result = LoadSubtitlesResult((asset,), SubtitleFormat.ASS)
    window._populate_mapping_table()
    window._update_actions()

    assert window.offset_button.isEnabled() is False
    assert window.lock_button.isEnabled() is False


def test_unlock_clears_manual_offset_and_saved_mapping_state(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, subtitle, _ = _prepared_mapping_window(qtbot, tmp_path)
    window.mapping_table.selectRow(0)
    window.locked_subtitles.add(subtitle)
    window.subtitle_offsets_90k[subtitle] = 11_250
    window.restored_mapping_locks = (
        MappingLock(
            "episode-1",
            "playlist:start",
            "playlist:end",
            MediaTick90k(11_250),
        ),
    )
    monkeypatch.setattr(window, "_schedule_mapping_preflight", lambda: None)

    window.toggle_rows_locked()

    assert subtitle not in window.locked_subtitles
    assert window.subtitle_offsets_90k[subtitle] == 0
    assert window.mapping_table.item(0, 7).text() == "0 ms"
    assert window.restored_mapping_locks == ()
    assert window.prepared is None
    saved = window._project_mappings()
    assert saved[0].manual_offset_90k == 0
    assert saved[0].locked is False


def test_project_mapping_uses_current_offset_before_repreflight(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, _, _ = _prepared_mapping_window(qtbot, tmp_path)
    window.mapping_table.selectRow(0)
    window.offset_spin.setValue(125)
    monkeypatch.setattr(window, "_schedule_mapping_preflight", lambda: None)

    window.apply_batch_offset()

    assert window.prepared is None
    saved = window._project_mappings()
    assert saved[0].manual_offset_90k == 11_250
    assert saved[0].locked is True


def test_invalidation_during_preflight_requests_a_fresh_run(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    window, _, _ = _prepared_mapping_window(qtbot, tmp_path)
    window.active_preflight_revision = window.preflight_revision
    window.pending_preflight = False

    window._invalidate_preflight()

    assert window.pending_preflight is True


def test_current_project_file_is_protected_from_subtitle_output(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    window, _, _ = _prepared_mapping_window(qtbot, tmp_path)
    project_path = tmp_path / "workspace.bdsm.json"
    window.project_path = project_path
    window.output_mode.setCurrentIndex(window.output_mode.findData("full_path"))
    window.output_path.setText(str(project_path))

    request = window._prepare_request()

    assert request is not None
    assert request.output_context is not None
    assert project_path in request.output_context.input_subtitle_paths
    output_preflight = preflight_outputs(
        request.output_targets,
        request.output_context,
        require_existing_sources=False,
    )
    assert "overwrites_input" in {issue.code for issue in output_preflight.errors}


def test_boundary_combo_creates_lock_and_schedules_mapping_preflight(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, subtitle, _ = _prepared_mapping_window(qtbot, tmp_path)
    scheduled: list[None] = []

    def schedule() -> None:
        scheduled.append(None)
        window.pending_preflight = True

    monkeypatch.setattr(window, "_schedule_mapping_preflight", schedule)
    start_combo = window.mapping_table.cellWidget(0, 4)
    assert isinstance(start_combo, QComboBox)

    start_combo.setCurrentIndex(start_combo.findData("user:middle"))

    assert window.restored_mapping_locks == (
        MappingLock(
            "episode-1",
            "user:middle",
            "playlist:end",
            MediaTick90k(9_000),
        ),
    )
    assert subtitle in window.locked_subtitles
    assert window.mapping_dirty is True
    assert window.pending_preflight is True
    assert scheduled == [None]


def test_stale_preflight_revision_does_not_overwrite_manual_mapping(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, _, stale_prepared = _prepared_mapping_window(qtbot, tmp_path)
    stale_revision = window.preflight_revision
    monkeypatch.setattr(window, "_schedule_mapping_preflight", lambda: None)

    window._apply_mapping_boundary("episode-1", "start", "user:middle")
    window.pending_preflight = False
    window._preflight_finished_for_revision(stale_prepared, stale_revision)

    assert window.prepared is None
    assert window.restored_mapping_locks == (
        MappingLock(
            "episode-1",
            "user:middle",
            "playlist:end",
            MediaTick90k(9_000),
        ),
    )
    assert window.mapping_dirty is True
    assert window.pending_preflight is True


def test_reset_mapping_clears_manual_mapping_state(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, subtitle, _ = _prepared_mapping_window(qtbot, tmp_path)
    window.locked_subtitles.add(subtitle)
    window.subtitle_offsets_90k[subtitle] = 11_250
    window.restored_mapping_locks = (
        MappingLock(
            "episode-1",
            "user:middle",
            "playlist:end",
            MediaTick90k(11_250),
        ),
    )
    window.restored_mapping_snapshots = (
        MappingSnapshot(
            "episode-1",
            "user:middle",
            "playlist:end",
            450_000,
            129_600_000,
            11_250,
            True,
            "high",
        ),
    )

    def schedule() -> None:
        window.pending_preflight = True

    monkeypatch.setattr(window, "_schedule_mapping_preflight", schedule)

    window.reset_automatic_mapping()

    assert window.restored_mapping_locks == ()
    assert window.subtitle_offsets_90k == {}
    assert window.locked_subtitles == set()
    assert window.timeline.user_boundaries == ()
    assert window.restored_mapping_snapshots == ()
    assert window.prepared is None
    assert window.mapping_dirty is True
    assert window.pending_preflight is True
