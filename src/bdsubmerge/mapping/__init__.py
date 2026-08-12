"""Deterministic, UI-independent episode mapping."""

from .boundaries import boundary, merge_boundaries
from .models import (
    BoundaryKind,
    BoundarySource,
    EpisodeMapping,
    EpisodeRequest,
    MappingConfidence,
    MappingCostConfig,
    MappingLock,
    MappingResult,
    MediaTick90k,
    TimelineBoundary,
)
from .solver import MappingError, auto_map_episodes

__all__ = [
    "BoundaryKind",
    "BoundarySource",
    "EpisodeMapping",
    "EpisodeRequest",
    "MappingConfidence",
    "MappingCostConfig",
    "MappingError",
    "MappingLock",
    "MappingResult",
    "MediaTick90k",
    "TimelineBoundary",
    "auto_map_episodes",
    "boundary",
    "merge_boundaries",
]
