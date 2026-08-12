"""Merge-plan primitives independent of filesystem and UI concerns."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MergeSource[DocumentT]:
    label: str
    document: DocumentT
    offset_ticks: int


@dataclass(frozen=True, slots=True)
class MergeOptions:
    playlist_end_ticks: int | None = None
    accept_script_info_conflicts: bool = False
    keep_events_ending_before_zero: bool = False
    clip_negative_starts: bool = True
    preserve_source_newline: bool = True


@dataclass(frozen=True, slots=True)
class MergePlan[DocumentT]:
    sources: tuple[MergeSource[DocumentT], ...]
    options: MergeOptions = MergeOptions()

    def __post_init__(self) -> None:
        if not self.sources:
            raise ValueError("merge plan requires at least one source")
        labels = [source.label for source in self.sources]
        if len(set(labels)) != len(labels):
            raise ValueError("merge source labels must be unique")
        if self.options.playlist_end_ticks is not None and self.options.playlist_end_ticks < 0:
            raise ValueError("playlist end cannot be negative")
