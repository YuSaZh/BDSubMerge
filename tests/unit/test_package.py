import sys
from pathlib import Path

import pytest

from bdsubmerge import __version__
from bdsubmerge.app import main as app_main
from bdsubmerge.cli import main


def test_version_is_available() -> None:
    assert __version__ == "1.0.2b1"


def test_empty_cli_succeeds() -> None:
    assert main([]) == 0


def test_gui_smoke_mode_starts_without_entering_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    assert app_main(["bdsubmerge-gui", "--smoke-test"]) == 0


def test_gui_smoke_mode_rejects_an_unexpected_version() -> None:
    assert (
        app_main(
            [
                "bdsubmerge-gui",
                "--smoke-test",
                "--expect-version",
                "9.9.9",
            ]
        )
        == 2
    )


def test_gui_can_capture_release_visual_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    destination = tmp_path / "release-ui.png"

    result = app_main(
        [
            "bdsubmerge-gui",
            "--capture-screenshot",
            str(destination),
            "--locale",
            "en_US",
            "--theme",
            "dark",
            "--expect-version",
            __version__,
        ]
    )

    assert result == 0
    assert destination.stat().st_size > 0


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows system-font handling")
def test_gui_capture_reports_a_missing_windows_font(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("SystemRoot", str(tmp_path / "missing-windows"))

    with pytest.raises(RuntimeError, match="could not load screenshot font"):
        app_main(
            [
                "bdsubmerge-gui",
                "--capture-screenshot",
                str(tmp_path / "release-ui.png"),
                "--locale",
                "zh_CN",
            ]
        )
