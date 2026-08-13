"""Shared application services for CLI and GUI surfaces."""

from .models import (
    ApplicationIssue,
    ApplicationSeverity,
    ExecuteMergeRequest,
    ExecuteMergeResult,
    InspectRequest,
    InspectResult,
    LoadSubtitlesRequest,
    LoadSubtitlesResult,
    PreparedMerge,
    PrepareMergeRequest,
    ScanRequest,
    ScanResult,
    SubtitleAsset,
    SubtitleInput,
)
from .playlist_selection import (
    JRIVER_INCOMPATIBLE_WARNING,
    PlaylistEquivalenceGroup,
    PlaylistSelectionRequest,
    PlaylistSelectionResult,
    select_playlists,
)
from .services import (
    BdmvApplicationService,
    MergeApplicationService,
    SubtitleApplicationService,
    build_playlist_boundaries,
)

__all__ = [
    "ApplicationIssue",
    "ApplicationSeverity",
    "BdmvApplicationService",
    "ExecuteMergeRequest",
    "ExecuteMergeResult",
    "InspectRequest",
    "InspectResult",
    "JRIVER_INCOMPATIBLE_WARNING",
    "LoadSubtitlesRequest",
    "LoadSubtitlesResult",
    "MergeApplicationService",
    "PlaylistEquivalenceGroup",
    "PlaylistSelectionRequest",
    "PlaylistSelectionResult",
    "PreparedMerge",
    "PrepareMergeRequest",
    "ScanRequest",
    "ScanResult",
    "SubtitleApplicationService",
    "SubtitleAsset",
    "SubtitleInput",
    "build_playlist_boundaries",
    "select_playlists",
]
