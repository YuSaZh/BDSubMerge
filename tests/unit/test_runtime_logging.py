import json
from pathlib import Path

import pytest

from bdsubmerge.runtime_logging import (
    configure_runtime_logging,
    default_log_directory,
    record_runtime_event,
    record_runtime_exception,
    shutdown_runtime_logging,
)


@pytest.mark.parametrize(
    ("platform_name", "environment", "expected"),
    (
        (
            "win32",
            {"LOCALAPPDATA": "C:/Users/Test/AppData/Local"},
            Path("C:/Users/Test/AppData/Local/BDSubMerge/logs"),
        ),
        (
            "darwin",
            {},
            Path("/Users/test/Library/Logs/BDSubMerge"),
        ),
        (
            "linux",
            {"XDG_STATE_HOME": "/state"},
            Path("/state/bdsubmerge/logs"),
        ),
    ),
)
def test_runtime_log_directory_uses_platform_user_data_location(
    platform_name: str,
    environment: dict[str, str],
    expected: Path,
) -> None:
    home = Path("/Users/test")

    result = default_log_directory(
        platform_name=platform_name,
        environ=environment,
        home=home,
    )

    assert result == expected


def test_structured_runtime_log_omits_subtitle_body_and_exception_message(
    tmp_path: Path,
) -> None:
    private_body = "private subtitle body must never be logged"
    log_path = configure_runtime_logging(tmp_path, reset=True)
    assert log_path is not None
    try:
        record_runtime_event(
            "subtitle_load_completed",
            source_path="episode.ass",
            event_count=1,
        )
        try:
            raise ValueError(private_body)
        except ValueError as error:
            record_runtime_exception("subtitle_load_failed", error)
    finally:
        shutdown_runtime_logging()

    raw = log_path.read_text(encoding="utf-8")
    records = tuple(json.loads(line) for line in raw.splitlines())
    assert private_body not in raw
    assert records[0]["event"] == "runtime_environment"
    assert records[0]["details"]["application_version"]
    assert records[0]["details"]["python_version"]
    assert records[1]["details"] == {
        "event_count": 1,
        "source_path": "episode.ass",
    }
    assert records[2]["details"]["error_type"] == "builtins.ValueError"
    assert records[2]["details"]["stack"]
