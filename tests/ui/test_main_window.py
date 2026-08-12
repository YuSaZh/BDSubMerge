from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSettings, Qt
from pytestqt.qtbot import QtBot

from bdsubmerge.application import (
    ApplicationIssue,
    ApplicationSeverity,
    LoadSubtitlesResult,
    PreparedMerge,
    ScanResult,
    SubtitleAsset,
)
from bdsubmerge.domain.models import (
    BdmvLayout,
    PlayItemInfo,
    PlaylistConfidence,
    PlaylistInfo,
    ReferenceStatus,
)
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.mapping import BoundaryKind, MappingLock
from bdsubmerge.output import (
    CollisionPolicy,
    OutputPreset,
    PreflightResult,
    ResolvedOutput,
)
from bdsubmerge.project import (
    FileFingerprint,
    OutputState,
    ProjectState,
    RestoredProject,
    SourceCheck,
    SourceState,
)
from bdsubmerge.subtitles import SubtitleFormat, TextSubtitleInfo, parse_ass
from bdsubmerge.ui.main_window import MainWindow


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
