from dataclasses import replace
from pathlib import Path

from bdsubmerge.application import (
    JRIVER_INCOMPATIBLE_WARNING,
    PlaylistSelectionRequest,
    PlaylistSelectionResult,
    select_playlists,
)
from bdsubmerge.domain.models import PlayItemInfo, PlaylistInfo, ReferenceStatus
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.output import JRiverOutputTarget, PlaylistOutputTarget


def _playlist(stem: str, clip_id: str, *, errors: tuple[str, ...] = ()) -> PlaylistInfo:
    item = PlayItemInfo(
        0,
        clip_id,
        "M2TS",
        0,
        45_000,
        MediaTick90k(0),
        MediaTick90k(90_000),
        0,
        False,
        0,
        1,
        ReferenceStatus(True, True),
    )
    fingerprint = ((clip_id, 0, 45_000, 0),)
    return PlaylistInfo(
        Path("BDMV") / "PLAYLIST" / f"{stem}.mpls",
        stem,
        MediaTick90k(90_000),
        (item,),
        (),
        errors=errors,
        timeline_fingerprint=fingerprint,
    )


def _codes(result: PlaylistSelectionResult) -> set[str]:
    return {issue.code for issue in result.issues}


def test_equivalent_playlists_are_compatible_and_need_no_explicit_primary() -> None:
    first = _playlist("00001", "00010")
    second = _playlist("00002", "00010")
    result = select_playlists(
        PlaylistSelectionRequest(
            (second, first),
            (JRiverOutputTarget("jriver"),),
        )
    )
    assert result.ready
    assert result.all_equivalent
    assert result.primary_playlist == first
    assert result.compatible_stems == ("00001", "00002")
    assert result.issues == ()


def test_ac10_non_equivalent_jriver_selection_requires_primary_and_warns_clearly() -> None:
    result = select_playlists(
        PlaylistSelectionRequest(
            (_playlist("00001", "00010"), _playlist("00002", "00020")),
            (JRiverOutputTarget("jriver"),),
        )
    )
    assert not result.ready
    assert result.primary_playlist is None
    assert "jriver_primary_required" in _codes(result)
    warning = next(
        issue for issue in result.issues if issue.code == "non_equivalent_jriver_timelines"
    )
    assert warning.message == JRIVER_INCOMPATIBLE_WARNING
    assert "index.ass" in warning.message
    assert "多个不等价播放列表" in warning.message


def test_explicit_primary_is_unique_and_compatible_only_with_its_group() -> None:
    equivalent = _playlist("00003", "00010")
    result = select_playlists(
        PlaylistSelectionRequest(
            (
                _playlist("00002", "00020"),
                equivalent,
                _playlist("00001", "00010"),
            ),
            jriver_enabled=True,
            primary_stem="00003",
        )
    )
    assert result.ready
    assert result.primary_playlist == equivalent
    assert result.compatible_stems == ("00001", "00003")
    assert "non_equivalent_jriver_timelines" in _codes(result)


def test_invalid_primary_is_blocking() -> None:
    result = select_playlists(
        PlaylistSelectionRequest(
            (_playlist("00001", "00010"), _playlist("00002", "00020")),
            (JRiverOutputTarget("jriver"),),
            primary_stem="99999",
        )
    )
    assert not result.ready
    assert "invalid_jriver_primary" in _codes(result)


def test_duplicate_and_unavailable_selections_are_blocking() -> None:
    playlist = _playlist("00001", "00010")
    duplicate = select_playlists(
        PlaylistSelectionRequest((playlist, playlist), jriver_enabled=True)
    )
    unavailable = select_playlists(
        PlaylistSelectionRequest(
            (replace(playlist, errors=("corrupt MPLS",)),),
            jriver_enabled=True,
            primary_stem="00001",
        )
    )
    assert not duplicate.ready
    assert "duplicate_playlist_selection" in _codes(duplicate)
    assert not unavailable.ready
    assert "playlist_unavailable" in _codes(unavailable)
    assert "invalid_jriver_primary" in _codes(unavailable)


def test_non_jriver_outputs_do_not_require_a_primary_timeline() -> None:
    result = select_playlists(
        PlaylistSelectionRequest(
            (_playlist("00001", "00010"), _playlist("00002", "00020")),
            (PlaylistOutputTarget("playlist"),),
        )
    )
    assert result.ready
    assert result.primary_playlist is None
    assert result.compatible_stems == ()
    assert result.issues == ()
