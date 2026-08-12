from pathlib import Path

import pytest

from bdsubmerge.bdmv.shinya_adapter import ShinyaPlaylistAdapter
from bdsubmerge.domain.models import BdmvLayout


@pytest.mark.contract
def test_shinya_import_and_constructor_are_isolated() -> None:
    """The adapter remains constructible without exposing raw Shinya classes."""
    adapter = ShinyaPlaylistAdapter()
    assert type(adapter).__module__ == "bdsubmerge.bdmv.shinya_adapter"


@pytest.mark.contract
def test_adapter_rejects_missing_required_play_item_fields(tmp_path: Path) -> None:
    bdmv = tmp_path / "BDMV"
    for name in ("PLAYLIST", "CLIPINF", "STREAM"):
        (bdmv / name).mkdir(parents=True, exist_ok=True)
    index = bdmv / "index.bdmv"
    index.touch()
    path = bdmv / "PLAYLIST" / "bad.mpls"
    path.touch()
    layout = BdmvLayout(
        tmp_path,
        tmp_path,
        bdmv,
        index,
        bdmv / "PLAYLIST",
        bdmv / "CLIPINF",
        bdmv / "STREAM",
    )
    adapter = ShinyaPlaylistAdapter(lambda _: {"PlayList": {"PlayItems": [{}]}})
    with pytest.raises(KeyError, match="ClipInformationFileName"):
        adapter.parse(path, layout)
