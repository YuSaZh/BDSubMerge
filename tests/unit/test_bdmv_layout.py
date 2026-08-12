from pathlib import Path

import pytest

from bdsubmerge.bdmv.layout import discover_bdmv_layouts, resolve_bdmv_layout


def _make_bdmv(root: Path) -> Path:
    bdmv = root / "BDMV"
    bdmv.mkdir(parents=True)
    (bdmv / "index.bdmv").touch()
    return bdmv


def test_disc_root_and_bdmv_input_resolve_to_same_index(tmp_path: Path) -> None:
    bdmv = _make_bdmv(tmp_path / "Title")
    from_root = resolve_bdmv_layout(tmp_path / "Title")
    from_bdmv = resolve_bdmv_layout(bdmv)
    assert from_root.index_bdmv_path == from_bdmv.index_bdmv_path
    assert from_root.disc_container_path == (tmp_path / "Title").resolve()


def test_discovers_multiple_nested_bdmv_layouts_without_selecting_first(tmp_path: Path) -> None:
    _make_bdmv(tmp_path / "A" / "BDROM")
    _make_bdmv(tmp_path / "B")
    layouts = discover_bdmv_layouts(tmp_path, max_depth=3)
    assert [layout.disc_container_path.name for layout in layouts] == ["BDROM", "B"]
    with pytest.raises(ValueError, match="Multiple BDMV"):
        resolve_bdmv_layout(tmp_path, max_depth=3)


def test_depth_limit_is_respected(tmp_path: Path) -> None:
    _make_bdmv(tmp_path / "one" / "two" / "three")
    assert discover_bdmv_layouts(tmp_path, max_depth=2) == ()
    assert discover_bdmv_layouts(tmp_path, max_depth=3) == ()
    assert len(discover_bdmv_layouts(tmp_path, max_depth=4)) == 1


def test_single_mpls_resolves_its_containing_layout(tmp_path: Path) -> None:
    bdmv = _make_bdmv(tmp_path / "Title")
    playlist = bdmv / "PLAYLIST"
    playlist.mkdir()
    mpls = playlist / "00000.mpls"
    mpls.touch()
    assert resolve_bdmv_layout(mpls).bdmv_path == bdmv.resolve()
