from pathlib import Path

from bdsubmerge.application import (
    append_discovered_subtitle_paths,
    discover_subtitle_paths,
)


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
