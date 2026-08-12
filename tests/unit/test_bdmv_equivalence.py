from dataclasses import replace
from pathlib import Path

from bdsubmerge.bdmv.equivalence import are_equivalent, group_equivalent
from bdsubmerge.bdmv.timeline import RawPlayItem, build_playlist


def _playlist(tmp_path: Path, name: str, clip: str, angle: int = 0):
    stream = tmp_path / "STREAM"
    clipinf = tmp_path / "CLIPINF"
    stream.mkdir(exist_ok=True)
    clipinf.mkdir(exist_ok=True)
    (stream / f"{clip}.m2ts").touch()
    (clipinf / f"{clip}.clpi").touch()
    return build_playlist(
        tmp_path / name,
        (RawPlayItem(clip, "M2TS", 10, 20, selected_angle=angle),),
        (),
        stream_path=stream,
        clipinf_path=clipinf,
    )


def test_equivalence_ignores_mpls_filename_but_includes_angle(tmp_path: Path) -> None:
    first = _playlist(tmp_path, "00001.mpls", "00001")
    second = _playlist(tmp_path, "00002.mpls", "00001")
    other_angle = _playlist(tmp_path, "00003.mpls", "00001", 1)
    assert are_equivalent(first, second)
    assert not are_equivalent(first, other_angle)
    assert len(group_equivalent((first, second, other_angle))) == 2


def test_unavailable_playlist_is_never_equivalent(tmp_path: Path) -> None:
    playlist = _playlist(tmp_path, "00001.mpls", "00001")
    unavailable = replace(playlist, errors=("bad MPLS",))
    assert not are_equivalent(unavailable, unavailable)
