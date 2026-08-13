from collections.abc import Callable
from pathlib import Path

import pytest

from bdsubmerge.application import (
    append_discovered_subtitle_paths,
    discover_subtitle_paths,
    natural_path_key,
)
from bdsubmerge.cancellation import OperationCancelledError


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"subtitle")
    return path


def test_discovers_supported_subtitles_recursively_in_natural_order(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Subtitles"
    episode_10 = _touch(root / "nested" / "E10.SUP")
    episode_2 = _touch(root / "nested" / "e2.SRT")
    episode_1 = _touch(root / "nested" / "E1.ass")
    special = _touch(root / "special.sSa")
    _touch(root / "notes.txt")

    discovered = discover_subtitle_paths((root,))

    assert discovered == (episode_1, episode_2, episode_10, special)


def test_mixed_inputs_are_sorted_and_duplicate_files_are_removed(tmp_path: Path) -> None:
    root = tmp_path / "Subtitles"
    episode_10 = _touch(root / "E10.ass")
    episode_2 = _touch(root / "E2.ass")
    episode_1 = _touch(root / "E1.ass")

    discovered = discover_subtitle_paths((episode_10, root, episode_1))

    assert discovered == (episode_1, episode_2, episode_10)


def test_append_preserves_manual_order_and_naturally_orders_only_new_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Subtitles"
    episode_10 = _touch(root / "E10.ass")
    episode_3 = _touch(root / "E3.ass")
    episode_2 = _touch(root / "E2.ass")
    episode_1 = _touch(root / "E1.ass")

    appended = append_discovered_subtitle_paths((episode_10, episode_1), (root,))

    assert appended == (episode_10, episode_1, episode_2, episode_3)


@pytest.mark.parametrize(
    ("names", "expected"),
    (
        (("EP10.ass", "EP02.ass", "EP01.ass"), ("EP01.ass", "EP02.ass", "EP10.ass")),
        (("10.ass", "2.ass", "1.ass"), ("1.ass", "2.ass", "10.ass")),
        (("Vol.10.ass", "Vol.2.ass", "Vol.1.ass"), ("Vol.1.ass", "Vol.2.ass", "Vol.10.ass")),
        (("10/E1.ass", "2/E1.ass", "1/E1.ass"), ("1/E1.ass", "2/E1.ass", "10/E1.ass")),
    ),
)
def test_natural_path_key_covers_release_naming_patterns(
    names: tuple[str, ...],
    expected: tuple[str, ...],
) -> None:
    ordered = tuple(
        str(path).replace("\\", "/")
        for path in sorted((Path(name) for name in names), key=natural_path_key)
    )

    assert ordered == expected


def test_discovery_checks_cancellation_while_walking(tmp_path: Path) -> None:
    root = tmp_path / "Subtitles"
    _touch(root / "nested" / "E1.ass")
    visited: list[Path] = []

    with pytest.raises(OperationCancelledError):
        discover_subtitle_paths(
            (root,),
            cancellation_check=lambda: bool(visited),
            progress=visited.append,
        )

    assert visited == [root]


def test_discovery_reports_walk_errors_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "Subtitles"
    episode = _touch(root / "E1.ass")
    errors: list[tuple[Path, OSError]] = []

    def walk_with_error(
        path: Path,
        *,
        onerror: Callable[[OSError], None],
    ) -> list[tuple[str, list[str], list[str]]]:
        onerror(PermissionError(13, "denied", str(path / "blocked")))
        return [(str(path), [], [episode.name])]

    monkeypatch.setattr("bdsubmerge.application.subtitle_discovery.os.walk", walk_with_error)

    discovered = discover_subtitle_paths(
        (root,),
        on_error=lambda path, error: errors.append((path, error)),
    )

    assert discovered == (episode,)
    assert errors[0][0] == root / "blocked"
