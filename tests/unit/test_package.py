from bdsubmerge import __version__
from bdsubmerge.cli import main


def test_version_is_available() -> None:
    assert __version__ == "0.1.0.dev0"


def test_empty_cli_succeeds() -> None:
    assert main([]) == 0
