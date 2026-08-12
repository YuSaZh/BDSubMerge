"""Timeline fingerprint comparison utilities."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from bdsubmerge.domain.models import PlaylistInfo, TimelineFingerprint


def timeline_fingerprint(playlist: PlaylistInfo) -> TimelineFingerprint:
    """Return the effective clip sequence independent of the MPLS filename."""
    return tuple(
        (item.clip_id, item.in_time_45k, item.out_time_45k, item.selected_angle)
        for item in playlist.play_items
    )


def are_equivalent(left: PlaylistInfo, right: PlaylistInfo) -> bool:
    """Compare two available playlists by their complete effective timeline."""
    both_available = left.is_available and right.is_available
    return both_available and timeline_fingerprint(left) == timeline_fingerprint(right)


def group_equivalent(playlists: Iterable[PlaylistInfo]) -> tuple[tuple[PlaylistInfo, ...], ...]:
    """Group available playlists by fingerprint, preserving deterministic ordering."""
    groups: defaultdict[TimelineFingerprint, list[PlaylistInfo]] = defaultdict(list)
    for playlist in playlists:
        if playlist.is_available:
            groups[timeline_fingerprint(playlist)].append(playlist)
    ordered = (
        tuple(sorted(group, key=lambda item: str(item.path).casefold()))
        for group in groups.values()
    )
    return tuple(sorted(ordered, key=lambda group: str(group[0].path).casefold()))
