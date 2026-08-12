from pathlib import Path

import pytest
from shinya.bd import MoviePlaylistFile

from bdsubmerge.bdmv.shinya_adapter import ShinyaPlaylistAdapter
from bdsubmerge.domain.models import BdmvLayout

FIXTURE = Path(__file__).parents[1] / "fixtures" / "shinya" / "minimal_playlist.mpls.hex"


def _fixture_bytes() -> bytes:
    lines = (
        line.strip()
        for line in FIXTURE.read_text(encoding="ascii").splitlines()
        if line and not line.startswith("#")
    )
    return bytes.fromhex("".join(lines))


def _layout(tmp_path: Path) -> BdmvLayout:
    bdmv = tmp_path / "BDMV"
    for name in ("PLAYLIST", "CLIPINF", "STREAM"):
        (bdmv / name).mkdir(parents=True, exist_ok=True)
    index = bdmv / "index.bdmv"
    index.touch()
    return BdmvLayout(
        tmp_path,
        tmp_path,
        bdmv,
        index,
        bdmv / "PLAYLIST",
        bdmv / "CLIPINF",
        bdmv / "STREAM",
    )


@pytest.mark.contract
def test_shinya_import_and_constructor_are_isolated() -> None:
    """The adapter remains constructible without exposing raw Shinya classes."""
    adapter = ShinyaPlaylistAdapter()
    assert type(adapter).__module__ == "bdsubmerge.bdmv.shinya_adapter"


@pytest.mark.contract
def test_adapter_rejects_missing_required_play_item_fields(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    path = layout.playlist_path / "bad.mpls"
    path.touch()
    adapter = ShinyaPlaylistAdapter(lambda _: {"PlayList": {"PlayItems": [{}]}})
    with pytest.raises(KeyError, match="ClipInformationFileName"):
        adapter.parse(path, layout)


@pytest.mark.contract
def test_real_shinya_parser_exposes_pinned_mpls_fields(tmp_path: Path) -> None:
    """Field contract derived from upstream commit 53998916, not media data."""
    assert MoviePlaylistFile.__module__ == "shinya.bd.mpls"

    path = tmp_path / "minimal.mpls"
    path.write_bytes(_fixture_bytes())

    parsed = MoviePlaylistFile(str(path))
    play_item = parsed.data["PlayList"]["PlayItems"][0]
    mark = parsed.data["PlayListMark"]["PlayListMarks"][0]

    assert play_item["ClipInformationFileName"] == "00001"
    assert play_item["ClipCodecIdentifier"] == "M2TS"
    assert play_item["INTime"] == 45_000
    assert play_item["OUTTime"] == 90_000
    assert play_item["ConnectionCondition"] == 1
    assert play_item["IsMultiAngle"] == 0
    assert play_item["STNTable"]["Length"] == 0
    assert mark["RefToPlayItemID"] == 0
    assert mark["MarkTimeStamp"] == 67_500


@pytest.mark.contract
def test_default_adapter_parses_real_shinya_object(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    path = layout.playlist_path / "00000.mpls"
    path.write_bytes(_fixture_bytes())
    (layout.stream_path / "00001.m2ts").touch()
    (layout.clipinf_path / "00001.clpi").touch()

    playlist = ShinyaPlaylistAdapter().parse(path, layout)

    assert playlist.stem == "00000"
    assert playlist.duration_90k == 90_000
    assert playlist.play_items[0].clip_id == "00001"
    assert playlist.play_items[0].codec_id == "M2TS"
    assert playlist.play_items[0].references.complete
    assert playlist.marks[0].play_item_index == 0
    assert playlist.marks[0].time_90k == 45_000
    assert playlist.errors == ()
