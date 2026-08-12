"""Injectable application-service dependencies."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from bdsubmerge.domain.models import BdmvLayout, PlaylistInfo


class PlaylistAdapter(Protocol):
    def parse(
        self,
        path: Path,
        layout: BdmvLayout,
        *,
        selected_angles: Mapping[int, int] | None = None,
    ) -> PlaylistInfo: ...


class BinaryReader(Protocol):
    def __call__(self, path: Path) -> bytes: ...
