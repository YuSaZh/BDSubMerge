from collections.abc import Mapping
from pathlib import Path

from bdsubmerge.application import (
    BdmvApplicationService,
    InspectRequest,
    ScanRequest,
)
from bdsubmerge.domain.models import BdmvLayout, PlaylistInfo
from bdsubmerge.domain.timebase import MediaTick90k


class StubPlaylistAdapter:
    def parse(
        self,
        path: Path,
        layout: BdmvLayout,
        *,
        selected_angles: Mapping[int, int] | None = None,
    ) -> PlaylistInfo:
        del layout, selected_angles
        return PlaylistInfo(
            path=path,
            stem=path.stem,
            duration_90k=MediaTick90k(60 * 90_000),
            play_items=(),
            marks=(),
        )


def _bdmv(root: Path) -> Path:
    bdmv = root / "BDMV"
    playlist = bdmv / "PLAYLIST"
    playlist.mkdir(parents=True)
    (bdmv / "index.bdmv").write_bytes(b"index")
    (playlist / "00001.mpls").write_bytes(b"mpls")
    (bdmv / "CLIPINF").mkdir()
    (bdmv / "STREAM").mkdir()
    return bdmv


def test_scan_resolves_layout_injects_adapter_and_ranks_playlists(tmp_path: Path) -> None:
    _bdmv(tmp_path / "Title")
    service = BdmvApplicationService(playlist_adapter=StubPlaylistAdapter())

    result = service.scan(ScanRequest(tmp_path / "Title"))

    assert result.layout is not None
    assert [playlist.stem for playlist in result.playlists] == ["00001"]
    inspected = service.inspect(InspectRequest(result, "00001"))
    assert inspected.playlist == result.playlists[0]


def test_scan_reports_missing_or_ambiguous_layout_without_raising(tmp_path: Path) -> None:
    service = BdmvApplicationService(playlist_adapter=StubPlaylistAdapter())
    missing = service.scan(ScanRequest(tmp_path / "missing"))
    assert missing.ready is False
    assert missing.issues[0].code == "bdmv_resolution_failed"

    _bdmv(tmp_path / "A")
    _bdmv(tmp_path / "B")
    ambiguous = service.scan(ScanRequest(tmp_path))
    assert ambiguous.layout is None
    assert ambiguous.issues[0].code == "bdmv_resolution_failed"
