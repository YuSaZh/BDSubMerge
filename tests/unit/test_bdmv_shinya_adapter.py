from pathlib import Path

from bdsubmerge.bdmv.shinya_adapter import ShinyaPlaylistAdapter, scan_playlists
from bdsubmerge.cancellation import progress_scope
from bdsubmerge.domain.models import BdmvLayout


def _layout(tmp_path: Path) -> BdmvLayout:
    bdmv = tmp_path / "BDMV"
    playlist = bdmv / "PLAYLIST"
    clipinf = bdmv / "CLIPINF"
    stream = bdmv / "STREAM"
    for directory in (playlist, clipinf, stream):
        directory.mkdir(parents=True, exist_ok=True)
    index = bdmv / "index.bdmv"
    index.touch()
    return BdmvLayout(tmp_path, tmp_path, bdmv, index, playlist, clipinf, stream)


def test_adapter_converts_parser_data_to_project_models(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    (layout.stream_path / "00001.m2ts").touch()
    (layout.clipinf_path / "00001.clpi").touch()
    path = layout.playlist_path / "00000.mpls"
    path.touch()
    parser_data = {
        "PlayList": {
            "PlayItems": [
                {
                    "ClipInformationFileName": "00001",
                    "ClipCodecIdentifier": "M2TS",
                    "INTime": 45_000,
                    "OUTTime": 90_000,
                    "ConnectionCondition": 1,
                    "IsMultiAngle": False,
                    "STNTable": {
                        "PrimaryPGStreamEntries": [
                            {
                                "StreamEntry": {"RefToStreamPID": 0x1200},
                                "StreamAttributes": {
                                    "StreamCodingType": 0x90,
                                    "LanguageCode": "jpn",
                                },
                            }
                        ]
                    },
                }
            ]
        },
        "PlayListMark": {
            "PlayListMarks": [
                {"MarkType": 1, "RefToPlayItemID": 0, "MarkTimeStamp": 67_500}
            ]
        },
    }
    result = ShinyaPlaylistAdapter(lambda _: {"data": parser_data}).parse(path, layout)
    assert result.duration_90k == 90_000
    assert result.marks[0].time_90k == 45_000
    assert result.play_items[0].primary_pg_streams[0].language == "jpn"


def test_scan_isolates_a_broken_mpls(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    for name in ("00000.mpls", "00001.mpls"):
        (layout.playlist_path / name).touch()

    class StubAdapter:
        def parse(self, path: Path, _: BdmvLayout):
            if path.stem == "00000":
                raise ValueError("corrupt")
            return ShinyaPlaylistAdapter(
                lambda __: {"PlayList": {"PlayItems": []}, "PlayListMark": {}}
            ).parse(path, layout)

    results = scan_playlists(layout, adapter=StubAdapter())
    assert len(results) == 2
    assert results[0].errors == ("ValueError: corrupt",)
    assert results[1].errors == ("Playlist total duration is zero",)


def test_scan_reports_current_playlist_path(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    path = layout.playlist_path / "00000.mpls"
    path.touch()
    progress: list[tuple[int, str]] = []

    with progress_scope(lambda value, detail: progress.append((value, detail))):
        scan_playlists(layout)

    assert any(detail == str(path) for _, detail in progress)
