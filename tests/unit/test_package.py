import pytest

from bdsubmerge import __version__
from bdsubmerge.app import main as app_main
from bdsubmerge.cli import main


def test_version_is_available() -> None:
    assert __version__ == "0.1.0.dev0"


def test_empty_cli_succeeds() -> None:
    assert main([]) == 0


def test_gui_smoke_mode_starts_without_entering_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    assert app_main(["bdsubmerge-gui", "--smoke-test"]) == 0
