"""Application contract for selecting playlists and a JRiver main timeline."""

from __future__ import annotations

from dataclasses import dataclass

from bdsubmerge.bdmv.equivalence import group_equivalent, timeline_fingerprint
from bdsubmerge.domain.models import PlaylistInfo
from bdsubmerge.output import OutputPreset, OutputTarget

from .models import ApplicationIssue, ApplicationSeverity

JRIVER_INCOMPATIBLE_WARNING = (
    "一份 index.ass 只能对应一条播放时间线。"
    "当前原盘包含多个不等价播放列表，从菜单进入其他标题时，该字幕可能无法正确匹配。"  # noqa: RUF001
)


@dataclass(frozen=True, slots=True)
class PlaylistSelectionRequest:
    selected_playlists: tuple[PlaylistInfo, ...]
    output_targets: tuple[OutputTarget, ...] = ()
    jriver_enabled: bool = False
    primary_stem: str | None = None

    @property
    def uses_jriver(self) -> bool:
        return self.jriver_enabled or any(
            target.preset is OutputPreset.JRIVER for target in self.output_targets
        )


@dataclass(frozen=True, slots=True)
class PlaylistEquivalenceGroup:
    fingerprint: tuple[tuple[str, int, int, int], ...]
    playlist_stems: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlaylistSelectionResult:
    selected_playlists: tuple[PlaylistInfo, ...]
    equivalence_groups: tuple[PlaylistEquivalenceGroup, ...]
    primary_playlist: PlaylistInfo | None
    compatible_stems: tuple[str, ...]
    issues: tuple[ApplicationIssue, ...] = ()

    @property
    def ready(self) -> bool:
        return bool(self.selected_playlists) and not any(
            issue.severity is ApplicationSeverity.ERROR for issue in self.issues
        )

    @property
    def all_equivalent(self) -> bool:
        return len(self.equivalence_groups) == 1


def select_playlists(request: PlaylistSelectionRequest) -> PlaylistSelectionResult:
    """Validate a deterministic playlist selection without performing output writes."""
    selected = tuple(
        sorted(request.selected_playlists, key=lambda item: (item.stem.casefold(), str(item.path)))
    )
    issues: list[ApplicationIssue] = []
    if not selected:
        issues.append(_error("no_playlists_selected", "at least one playlist must be selected"))
        return PlaylistSelectionResult((), (), None, (), tuple(issues))

    path_keys = tuple(str(item.path).casefold() for item in selected)
    stem_keys = tuple(item.stem.casefold() for item in selected)
    if len(set(path_keys)) != len(path_keys) or len(set(stem_keys)) != len(stem_keys):
        issues.append(
            _error(
                "duplicate_playlist_selection",
                "the same playlist cannot be selected more than once",
            )
        )
    playlist_directories = {str(item.path.parent).casefold() for item in selected}
    if len(playlist_directories) > 1:
        issues.append(
            _error(
                "mixed_bdmv_selection",
                "selected playlists must belong to the same BDMV PLAYLIST directory",
            )
        )
    unavailable = tuple(item for item in selected if not item.is_available)
    for playlist in unavailable:
        issues.append(
            _error(
                "playlist_unavailable",
                f"selected playlist {playlist.stem!r} is unavailable",
                str(playlist.path),
            )
        )

    groups = _equivalence_groups(selected) if not unavailable else ()
    matches = _primary_matches(selected, request.primary_stem)
    primary: PlaylistInfo | None = None
    if request.primary_stem is not None:
        if len(matches) != 1:
            issues.append(
                _error(
                    "invalid_jriver_primary",
                    f"JRiver primary timeline {request.primary_stem!r} is not one unique "
                    "selected available playlist",
                )
            )
        elif not matches[0].is_available:
            issues.append(
                _error(
                    "invalid_jriver_primary",
                    f"JRiver primary timeline {request.primary_stem!r} is unavailable",
                    str(matches[0].path),
                )
            )
        else:
            primary = matches[0]

    if request.uses_jriver and not unavailable:
        if len(groups) > 1:
            issues.append(
                ApplicationIssue(
                    ApplicationSeverity.WARNING,
                    "non_equivalent_jriver_timelines",
                    JRIVER_INCOMPATIBLE_WARNING,
                )
            )
            if request.primary_stem is None:
                issues.append(
                    _error(
                        "jriver_primary_required",
                        "multiple non-equivalent playlists require one explicit JRiver "
                        "primary timeline",
                    )
                )
        elif request.primary_stem is None:
            primary = selected[0]
    elif request.primary_stem is not None and not request.uses_jriver:
        issues.append(
            _error(
                "jriver_primary_without_output",
                "a JRiver primary timeline requires a JRiver output target",
            )
        )

    compatible = _compatible_stems(primary, groups)
    return PlaylistSelectionResult(selected, groups, primary, compatible, tuple(issues))


def _equivalence_groups(
    playlists: tuple[PlaylistInfo, ...],
) -> tuple[PlaylistEquivalenceGroup, ...]:
    return tuple(
        PlaylistEquivalenceGroup(
            timeline_fingerprint(group[0]),
            tuple(item.stem for item in group),
        )
        for group in group_equivalent(playlists)
    )


def _primary_matches(
    playlists: tuple[PlaylistInfo, ...],
    primary_stem: str | None,
) -> tuple[PlaylistInfo, ...]:
    if primary_stem is None:
        return ()
    folded = primary_stem.casefold()
    return tuple(item for item in playlists if item.stem.casefold() == folded)


def _compatible_stems(
    primary: PlaylistInfo | None,
    groups: tuple[PlaylistEquivalenceGroup, ...],
) -> tuple[str, ...]:
    if primary is None:
        return ()
    folded = primary.stem.casefold()
    for group in groups:
        if any(stem.casefold() == folded for stem in group.playlist_stems):
            return group.playlist_stems
    return ()


def _error(code: str, message: str, source: str | None = None) -> ApplicationIssue:
    return ApplicationIssue(ApplicationSeverity.ERROR, code, message, source)
