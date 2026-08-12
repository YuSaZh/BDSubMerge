"""Generate a deterministic offscreen workspace screenshot in GitHub Actions."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

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
from bdsubmerge.ui import MainWindow

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


def main(destination: Path) -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    settings = QSettings(str(destination.with_suffix(".ini")), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    window.resize(1440, 1000)
    window.path_edit.setText(str(Path("D:/Anime/示例原盘")))
    window._scan_finished(_scan_state(Path("D:/Anime")))
    application.processEvents()
    loader = SubtitleApplicationService(read_bytes=lambda _: ASS)
    subtitles = loader.load_ordered(
        LoadSubtitlesRequest(
            (
                SubtitleInput(Path("D:/Anime/Subtitles/E01.ass")),
                SubtitleInput(Path("D:/Anime/Subtitles/E02.ass")),
            )
        )
    )
    window._subtitles_finished(subtitles)
    window.timeline.add_user_boundary(24 * 60 * SECOND)
    window.show()
    application.processEvents()
    destination.parent.mkdir(parents=True, exist_ok=True)
    image = window.grab().toImage()
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
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
