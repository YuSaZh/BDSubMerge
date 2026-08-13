"""Generate a deterministic offscreen workspace screenshot in GitHub Actions."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QComboBox

from bdsubmerge.application import (
    LoadSubtitlesRequest,
    ScanResult,
    SubtitleApplicationService,
    SubtitleInput,
)
from bdsubmerge.domain.models import (
    BdmvLayout,
    PlayItemInfo,
    PlaylistConfidence,
    PlaylistInfo,
    PlaylistMarkInfo,
    ReferenceStatus,
)
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.ui import MainWindow, ThemeMode

SECOND = 90_000
ASS = (
    b"[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
    b"[V4+ Styles]\nFormat: Name\nStyle: Default\n"
    b"[Events]\nFormat: Start, End, Style, Text\n"
    b"Dialogue: 0:00:00.00,0:23:42.00,Default,line\n"
)


def _scan_state(root: Path) -> ScanResult:
    bdmv = root / "示例原盘" / "BDMV"
    layout = BdmvLayout(
        root / "示例原盘",
        root / "示例原盘",
        bdmv,
        bdmv / "index.bdmv",
        bdmv / "PLAYLIST",
        bdmv / "CLIPINF",
        bdmv / "STREAM",
    )
    first_end = 24 * 60 * SECOND
    items = (
        PlayItemInfo(
            0,
            "00001",
            "M2TS",
            0,
            first_end // 2,
            MediaTick90k(0),
            MediaTick90k(first_end),
            1,
            False,
            0,
            1,
            ReferenceStatus(True, True),
        ),
        PlayItemInfo(
            1,
            "00002",
            "M2TS",
            0,
            first_end // 2,
            MediaTick90k(first_end),
            MediaTick90k(first_end * 2),
            1,
            False,
            0,
            1,
            ReferenceStatus(True, True),
        ),
    )
    playlist = PlaylistInfo(
        layout.playlist_path / "00001.mpls",
        "00001",
        MediaTick90k(first_end * 2),
        items,
        (
            PlaylistMarkInfo(0, 1, 0, 0, MediaTick90k(0)),
            PlaylistMarkInfo(1, 1, 1, 0, MediaTick90k(first_end)),
        ),
        score=96,
        confidence=PlaylistConfidence.HIGH,
    )
    alternate = PlaylistInfo(
        layout.playlist_path / "00002.mpls",
        "00002",
        MediaTick90k(first_end),
        items[:1],
        (),
        score=71,
        confidence=PlaylistConfidence.MEDIUM,
    )
    return ScanResult(layout, (playlist, alternate))


def _populate_workspace(window: MainWindow, destination: Path) -> None:
    fixture_root = destination.parent / "ui-fixture"
    (fixture_root / "示例原盘" / "BDMV").mkdir(parents=True, exist_ok=True)
    window.path_edit.setText(str(fixture_root / "示例原盘"))
    window._scan_finished(_scan_state(fixture_root))
    loader = SubtitleApplicationService(read_bytes=lambda _: ASS)
    subtitles = loader.load_ordered(
        LoadSubtitlesRequest(
            (
                SubtitleInput(fixture_root / "字幕" / "第01集.ass"),
                SubtitleInput(fixture_root / "字幕" / "第02集.ass"),
            )
        )
    )
    window._subtitles_finished(subtitles)
    window.timeline.set_user_boundaries(
        (("user:episode-split", 24 * 60 * SECOND),)
    )
    window.report_enabled.setChecked(True)
    window.report_path.setText(str(destination.parent / "merge-report.json"))
    request = window._prepare_request()
    if request is None:
        raise RuntimeError("UI fixture could not create a merge request")
    prepared = window.merge_service.prepare(
        replace(request, require_existing_sources=False)
    )
    if not prepared.ready:
        issues = ", ".join(issue.code for issue in prepared.issues)
        raise RuntimeError(f"UI fixture preflight is not ready: {issues}")
    window._preflight_finished(prepared)
    window.mapping_table.selectRow(0)
    window.task_status.setText(window.translations.text("task.complete"))
    window.progress.setValue(100)


def _assert_workspace_ready(window: MainWindow) -> None:
    prepared = window.prepared
    if prepared is None or not prepared.ready or prepared.report is None:
        raise RuntimeError("workspace screenshot does not show a ready preflight")
    if window.mapping_table.rowCount() != 2:
        raise RuntimeError("workspace screenshot must show two mapped subtitles")
    expected_output_headers = tuple(
        window.translations.text(key)
        for key in (
            "output.target_id",
            "output.mode",
            "output.path",
            "output.format",
            "output.encoding",
            "output.collision",
            "output.backup",
        )
    )
    output_headers = tuple(
        window.output_targets_table.horizontalHeaderItem(column).text()
        for column in range(window.output_targets_table.columnCount())
    )
    if output_headers != expected_output_headers:
        raise RuntimeError("workspace output summary columns are incomplete")
    output_values = tuple(
        window.output_targets_table.item(0, column).text()
        for column in range(window.output_targets_table.columnCount())
    )
    if not all(output_values):
        raise RuntimeError("workspace output summary values are incomplete")
    for row in range(window.mapping_table.rowCount()):
        start = window.mapping_table.cellWidget(row, 4)
        end = window.mapping_table.cellWidget(row, 5)
        confidence = window.mapping_table.item(row, 8)
        status = window.mapping_table.item(row, 9)
        if (
            not isinstance(start, QComboBox)
            or not start.currentData()
            or not isinstance(end, QComboBox)
            or not end.currentData()
            or confidence is None
            or not confidence.text()
            or status is None
            or not status.text()
        ):
            raise RuntimeError(f"workspace mapping row {row} is incomplete")
    if not window.generate_button.isEnabled():
        raise RuntimeError("workspace screenshot must show generation enabled")
    if window.active_task is not None:
        raise RuntimeError("workspace screenshot still has an active background task")
    if window.pending_preflight or window.mapping_preflight_timer.isActive():
        raise RuntimeError("workspace screenshot still has a pending preflight")
    summary = window.preflight_summary.toPlainText()
    required = (
        window.translations.text("preflight.ready"),
        window.translations.text(
            "preflight.expected_events",
            count=prepared.report.output_event_count,
        ),
        window.translations.text(
            "preflight.expected_styles",
            count=prepared.report.output_style_count,
        ),
        "index.ass",
        "merge-report.json",
    )
    missing = tuple(text for text in required if text not in summary)
    if missing:
        raise RuntimeError(f"workspace summary is missing expected text: {missing}")


def _capture(
    destination: Path,
    *,
    locale: str,
    theme: ThemeMode,
    minimum_device_pixel_ratio: float,
) -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    settings = QSettings(str(destination.with_suffix(".ini")), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    window.set_language(locale)
    window.set_theme(theme)
    window.resize(1440, 1000)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _populate_workspace(window, destination)
    window.show()
    application.processEvents()
    _assert_workspace_ready(window)
    pixmap = window.grab()
    device_pixel_ratio = pixmap.devicePixelRatio()
    if device_pixel_ratio < minimum_device_pixel_ratio:
        raise RuntimeError(
            "unexpected device pixel ratio: "
            f"{device_pixel_ratio} < {minimum_device_pixel_ratio}"
        )
    image = pixmap.toImage()
    if image.width() < 1200 or image.height() < 800:
        raise RuntimeError(f"unexpected screenshot size: {image.width()}x{image.height()}")
    sample_colors = {
        image.pixelColor(x, y).rgba()
        for x in range(0, image.width(), 32)
        for y in range(0, image.height(), 32)
    }
    if len(sample_colors) < 8:
        raise RuntimeError("workspace screenshot appears blank")
    if not image.save(str(destination), "PNG"):
        raise RuntimeError(f"could not save UI screenshot: {destination}")
    print(
        f"saved {destination} ({image.width()}x{image.height()}, "
        f"dpr={device_pixel_ratio}, locale={locale}, theme={theme.value})"
    )
    window.close()
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--locale", choices=("zh_CN", "en_US"), required=True)
    parser.add_argument(
        "--theme",
        choices=tuple(mode.value for mode in ThemeMode),
        required=True,
    )
    parser.add_argument("--minimum-device-pixel-ratio", type=float, default=1.0)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _parse_args()
    raise SystemExit(
        _capture(
            arguments.destination,
            locale=arguments.locale,
            theme=ThemeMode(arguments.theme),
            minimum_device_pixel_ratio=arguments.minimum_device_pixel_ratio,
        )
    )
