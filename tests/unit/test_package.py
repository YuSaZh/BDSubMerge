import pytest

from bdsubmerge import __version__
from bdsubmerge.app import main as app_main
from bdsubmerge.cli import main


def test_version_is_available() -> None:
    assert __version__ == "0.1.0.dev0"


def test_empty_cli_succeeds() -> None:
    assert main([]) == 0


def test_unimplemented_ui_exits_with_clear_message() -> None:
    with pytest.raises(SystemExit, match="desktop UI is not implemented"):
        app_main()
