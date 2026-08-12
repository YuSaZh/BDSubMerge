"""Read-only discovery of Blu-ray directory layouts."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from bdsubmerge.domain.models import BdmvLayout

DEFAULT_MAX_DEPTH = 3


def _case_insensitive_child(directory: Path, name: str) -> Path | None:
    expected = name.casefold()
    try:
        return next(
            (child for child in directory.iterdir() if child.name.casefold() == expected),
            None,
        )
    except (OSError, PermissionError):
        return None


def _layout_from_index(selected_path: Path, index_path: Path) -> BdmvLayout | None:
    if index_path.name.casefold() != "index.bdmv" or not index_path.is_file():
        return None
    bdmv_path = index_path.parent
    if bdmv_path.name.casefold() != "bdmv":
        return None
    playlist_path = _case_insensitive_child(bdmv_path, "PLAYLIST") or bdmv_path / "PLAYLIST"
    clipinf_path = _case_insensitive_child(bdmv_path, "CLIPINF") or bdmv_path / "CLIPINF"
    stream_path = _case_insensitive_child(bdmv_path, "STREAM") or bdmv_path / "STREAM"
    return BdmvLayout(
        selected_path=selected_path.resolve(strict=False),
        disc_container_path=bdmv_path.parent.resolve(strict=False),
        bdmv_path=bdmv_path.resolve(strict=False),
        index_bdmv_path=index_path.resolve(strict=False),
        playlist_path=playlist_path.resolve(strict=False),
        clipinf_path=clipinf_path.resolve(strict=False),
        stream_path=stream_path.resolve(strict=False),
    )


def _direct_layout(selected_path: Path) -> BdmvLayout | None:
    if selected_path.is_file():
        if selected_path.suffix.casefold() == ".mpls":
            playlist_dir = selected_path.parent
            bdmv_dir = playlist_dir.parent
            index_path = _case_insensitive_child(bdmv_dir, "index.bdmv")
            return _layout_from_index(selected_path, index_path) if index_path else None
        return _layout_from_index(selected_path, selected_path)

    index_path = _case_insensitive_child(selected_path, "index.bdmv")
    if index_path:
        layout = _layout_from_index(selected_path, index_path)
        if layout:
            return layout
    bdmv_dir = _case_insensitive_child(selected_path, "BDMV")
    if bdmv_dir:
        index_path = _case_insensitive_child(bdmv_dir, "index.bdmv")
        if index_path:
            return _layout_from_index(selected_path, index_path)
    return None


def discover_bdmv_layouts(
    selected_path: str | Path,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> tuple[BdmvLayout, ...]:
    """Find every BDMV at or below a selected path up to ``max_depth``."""
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    selected = Path(selected_path)
    if not selected.exists():
        return ()
    direct = _direct_layout(selected)
    if selected.is_file():
        return (direct,) if direct else ()

    found: dict[str, BdmvLayout] = {}
    if direct:
        found[str(direct.index_bdmv_path).casefold()] = direct

    queue: deque[tuple[Path, int]] = deque([(selected, 0)])
    while queue:
        directory, depth = queue.popleft()
        if depth > max_depth:
            continue
        index_path = _case_insensitive_child(directory, "index.bdmv")
        if index_path:
            layout = _layout_from_index(selected, index_path)
            if layout:
                found[str(layout.index_bdmv_path).casefold()] = layout
        if depth == max_depth:
            continue
        try:
            children = sorted(
                (child for child in directory.iterdir() if child.is_dir()),
                key=lambda child: child.name.casefold(),
            )
        except (OSError, PermissionError):
            continue
        queue.extend((child, depth + 1) for child in children)
    return tuple(sorted(found.values(), key=lambda item: str(item.index_bdmv_path).casefold()))


def resolve_bdmv_layout(
    selected_path: str | Path,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> BdmvLayout:
    """Resolve an unambiguous input; require selection when multiple discs exist."""
    layouts = discover_bdmv_layouts(selected_path, max_depth=max_depth)
    if not layouts:
        raise FileNotFoundError(f"No BDMV/index.bdmv found under {selected_path}")
    if len(layouts) > 1:
        message = f"Multiple BDMV layouts found under {selected_path}; choose one explicitly"
        raise ValueError(message)
    return layouts[0]
