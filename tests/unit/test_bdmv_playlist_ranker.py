from dataclasses import replace
from pathlib import Path

from bdsubmerge.bdmv.playlist_ranker import RankingContext, rank_playlists
from bdsubmerge.bdmv.timeline import RawPlayItem, build_playlist
from bdsubmerge.domain.models import PlaylistConfidence
from bdsubmerge.domain.timebase import MediaTick90k


def _playlist(tmp_path: Path, name: str, durations: tuple[int, ...]):
    stream = tmp_path / "STREAM"
    clipinf = tmp_path / "CLIPINF"
    stream.mkdir(exist_ok=True)
    clipinf.mkdir(exist_ok=True)
    items = []
    for index, duration in enumerate(durations):
        clip = f"{index:05}"
        (stream / f"{clip}.m2ts").touch()
        (clipinf / f"{clip}.clpi").touch()
        items.append(RawPlayItem(clip, "M2TS", 0, duration))
    return build_playlist(
        tmp_path / name,
        tuple(items),
        (),
        stream_path=stream,
        clipinf_path=clipinf,
    )


def test_ranking_uses_multiple_factors_and_explains_score(tmp_path: Path) -> None:
    main = _playlist(tmp_path, "00001.mpls", (45_000 * 600, 45_000 * 600))
    short = _playlist(tmp_path, "00002.mpls", (45_000,))
    ranked = rank_playlists(
        (short, main),
        RankingContext(
            subtitle_total_duration_90k=MediaTick90k(45_000 * 1200 * 2),
            subtitle_count=2,
        ),
    )
    assert ranked[0].stem == "00001"
    assert ranked[0].recommendation_reasons
    assert ranked[0].confidence in {PlaylistConfidence.MEDIUM, PlaylistConfidence.HIGH}


def test_unavailable_playlist_sorts_last(tmp_path: Path) -> None:
    valid = _playlist(tmp_path, "00001.mpls", (45_000,))
    invalid = replace(valid, path=tmp_path / "00002.mpls", stem="00002", errors=("bad",))
    ranked = rank_playlists((invalid, valid))
    assert ranked[-1].stem == "00002"
    assert ranked[-1].confidence is PlaylistConfidence.UNAVAILABLE
