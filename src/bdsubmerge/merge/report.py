"""Structured, serializable merge diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json


@dataclass(frozen=True, slots=True)
class MergeNotice:
    severity: str
    code: str
    message: str
    source_label: str | None = None


@dataclass(frozen=True, slots=True)
class StyleRenameRecord:
    source_label: str
    old_name: str
    new_name: str


@dataclass(frozen=True, slots=True)
class MergeReport:
    source_labels: tuple[str, ...]
    input_event_count: int
    output_event_count: int
    dropped_event_count: int = 0
    clipped_event_count: int = 0
    style_renames: tuple[StyleRenameRecord, ...] = ()
    notices: tuple[MergeNotice, ...] = ()
    metadata: dict[str, str | int | bool] = field(default_factory=dict)

    @property
    def errors(self) -> tuple[MergeNotice, ...]:
        return tuple(notice for notice in self.notices if notice.severity == "error")

    @property
    def warnings(self) -> tuple[MergeNotice, ...]:
        return tuple(notice for notice in self.notices if notice.severity == "warning")

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=indent, sort_keys=True)
