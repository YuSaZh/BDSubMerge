from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

import bdsubmerge.application.services as services_module
from bdsubmerge.application import (
    BdmvApplicationService,
    LoadSubtitlesRequest,
    MergeApplicationService,
    PrepareMergeRequest,
    ScanRequest,
    SubtitleApplicationService,
    SubtitleInput,
)
from bdsubmerge.cancellation import OperationCancelledError
from bdsubmerge.domain.models import (
    BdmvLayout,
    PlayItemInfo,
    PlaylistInfo,
    ReferenceStatus,
)
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.output import (
    CollisionPolicy,
    FullPathOutputTarget,
    OutputContext,
    ResolvedOutput,
    preflight_outputs,
    write_outputs_atomically,
)
from bdsubmerge.subtitles import parse_sup

ASS = (
    b"[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
    b"[V4+ Styles]\nFormat: Name\nStyle: Default\n"
    b"[Events]\nFormat: Start, End, Style, Text\n"
    b"Dialogue: 0:00:00.00,0:01:00.00,Default,line\n"
)


def _pg_packet(pts: int, segment_type: int) -> bytes:
    return b"".join(
        (
            b"PG",
            pts.to_bytes(4, "big"),
            pts.to_bytes(4, "big"),
            bytes((segment_type,)),
            (0).to_bytes(2, "big"),
        )
    )


def _layout(root: Path, *, playlist_count: int = 1) -> BdmvLayout:
    bdmv = root / "BDMV"
    playlist_path = bdmv / "PLAYLIST"
    playlist_path.mkdir(parents=True)
    (bdmv / "CLIPINF").mkdir()
    (bdmv / "STREAM").mkdir()
    index_path = bdmv / "index.bdmv"
    index_path.write_bytes(b"index")
    for index in range(playlist_count):
        (playlist_path / f"{index + 1:05d}.mpls").write_bytes(b"mpls")
    return BdmvLayout(
        root,
        root,
        bdmv,
        index_path,
        playlist_path,
        bdmv / "CLIPINF",
        bdmv / "STREAM",
    )


def _playlist(layout: BdmvLayout) -> PlaylistInfo:
    item = PlayItemInfo(
        0,
        "00001",
        "M2TS",
        0,
        2_700_000,
        MediaTick90k(0),
        MediaTick90k(60 * 90_000),
        1,
        False,
        0,
        1,
        ReferenceStatus(True, True),
    )
    return PlaylistInfo(
        layout.playlist_path / "00001.mpls",
        "00001",
        MediaTick90k(60 * 90_000),
        (item,),
        (),
    )


def test_playlist_scan_stops_between_mpls_files(tmp_path: Path) -> None:
    layout = _layout(tmp_path / "Title", playlist_count=2)
    cancelled = False
    parsed: list[str] = []

    class CancellingAdapter:
        def parse(
            self,
            path: Path,
            bdmv_layout: BdmvLayout,
            *,
            selected_angles: Mapping[int, int] | None = None,
        ) -> PlaylistInfo:
            nonlocal cancelled
            del bdmv_layout, selected_angles
            parsed.append(path.name)
            cancelled = True
            return PlaylistInfo(path, path.stem, MediaTick90k(90_000), (), ())

    with pytest.raises(OperationCancelledError):
        BdmvApplicationService(playlist_adapter=CancellingAdapter()).scan(
            ScanRequest(layout.selected_path),
            cancellation_check=lambda: cancelled,
        )

    assert parsed == ["00001.mpls"]


def test_sup_parser_checks_cancellation_between_packets() -> None:
    data = _pg_packet(90_000, 0x16) + _pg_packet(90_000, 0x80)
    checks = 0

    def cancel_before_second_packet() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 2

    with pytest.raises(OperationCancelledError):
        parse_sup(data, cancellation_check=cancel_before_second_packet)


def test_ordered_subtitle_load_stops_after_cancelled_read(tmp_path: Path) -> None:
    first = tmp_path / "01.ass"
    second = tmp_path / "02.ass"
    cancelled = False
    reads: list[Path] = []

    def read(path: Path) -> bytes:
        nonlocal cancelled
        reads.append(path)
        cancelled = True
        return ASS

    request = LoadSubtitlesRequest((SubtitleInput(first), SubtitleInput(second)))
    with pytest.raises(OperationCancelledError):
        SubtitleApplicationService(read_bytes=read).load_ordered(
            request,
            cancellation_check=lambda: cancelled,
        )

    assert reads == [first]


def test_prepare_honors_cancellation_after_output_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layout = _layout(tmp_path / "Title")
    playlist = _playlist(layout)
    subtitle_path = tmp_path / "episode.ass"
    subtitle_path.write_bytes(ASS)
    subtitles = SubtitleApplicationService(read_bytes=lambda _: ASS).load_ordered(
        LoadSubtitlesRequest((SubtitleInput(subtitle_path),))
    )
    destination = tmp_path / "output.ass"
    cancelled = False
    real_preflight = services_module.preflight_outputs

    def cancelling_preflight(*args: object, **kwargs: object):
        nonlocal cancelled
        result = real_preflight(*args, **kwargs)
        cancelled = True
        return result

    monkeypatch.setattr(services_module, "preflight_outputs", cancelling_preflight)
    with pytest.raises(OperationCancelledError):
        MergeApplicationService().prepare(
            PrepareMergeRequest(
                layout,
                playlist,
                subtitles,
                (FullPathOutputTarget("output", path=destination),),
                accept_low_confidence=True,
            ),
            cancellation_check=lambda: cancelled,
        )

    assert not destination.exists()


def test_cancellation_before_commit_removes_all_staged_files(tmp_path: Path) -> None:
    targets = (
        FullPathOutputTarget("first", path=tmp_path / "first.ass"),
        FullPathOutputTarget("second", path=tmp_path / "second.ass"),
    )
    preflight = preflight_outputs(targets, OutputContext(subtitle_format="ass"))
    cancelled = False

    def cancel_during_validation(path: Path, output: ResolvedOutput) -> None:
        nonlocal cancelled
        del path, output
        cancelled = True

    with pytest.raises(OperationCancelledError):
        write_outputs_atomically(
            preflight,
            {"first": b"one", "second": b"two"},
            validator=cancel_during_validation,
            cancellation_check=lambda: cancelled,
        )

    assert list(tmp_path.iterdir()) == []


def test_cancellation_during_commit_rolls_back_the_output_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.ass"
    first.write_bytes(b"old")
    targets = (
        FullPathOutputTarget("first", CollisionPolicy.OVERWRITE, path=first),
        FullPathOutputTarget("second", path=tmp_path / "second.ass"),
    )
    preflight = preflight_outputs(targets, OutputContext(subtitle_format="ass"))
    cancelled = False
    real_replace = Path.replace

    def cancel_after_first_commit(source: Path, destination: Path) -> Path:
        nonlocal cancelled
        result = real_replace(source, destination)
        if source.name.endswith(".tmp") and destination == first:
            cancelled = True
        return result

    monkeypatch.setattr(Path, "replace", cancel_after_first_commit)
    with pytest.raises(OperationCancelledError):
        write_outputs_atomically(
            preflight,
            {"first": b"new", "second": b"new"},
            cancellation_check=lambda: cancelled,
        )

    assert first.read_bytes() == b"old"
    assert not (tmp_path / "second.ass").exists()
    assert not tuple(tmp_path.glob(".*.tmp"))
    assert not tuple(tmp_path.glob(".*.rollback"))
