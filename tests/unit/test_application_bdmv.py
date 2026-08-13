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


class MutatingPlaylistAdapter(StubPlaylistAdapter):
    def __init__(self, *, remove: bool) -> None:
        self.remove = remove

    def parse(
        self,
        path: Path,
        layout: BdmvLayout,
        *,
        selected_angles: Mapping[int, int] | None = None,
    ) -> PlaylistInfo:
        parsed = super().parse(
            path,
            layout,
            selected_angles=selected_angles,
        )
        if self.remove:
            path.unlink()
        else:
            path.write_bytes(path.read_bytes() + b"changed")
        return parsed


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
    assert result.layout.index_fingerprint is not None
    assert result.layout.index_fingerprint.size == len(b"index")
    assert result.playlists[0].source_fingerprint is not None
    assert result.playlists[0].source_fingerprint.size == len(b"mpls")
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


def test_scan_reports_mpls_changed_or_missing_during_parse(tmp_path: Path) -> None:
    for remove, expected_code in (
        (False, "source_changed_during_scan"),
        (True, "source_missing_during_scan"),
    ):
        root = tmp_path / expected_code
        _bdmv(root)
        result = BdmvApplicationService(
            playlist_adapter=MutatingPlaylistAdapter(remove=remove)
        ).scan(ScanRequest(root))

        assert result.ready is False
        assert expected_code in {issue.code for issue in result.issues}
        assert result.playlists[0].is_available is False
