"""Isolation layer between Shinya's MPLS structures and project models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

from bdsubmerge.bdmv.timeline import RawPlayItem, RawPlaylistMark, build_playlist
from bdsubmerge.cancellation import (
    CancellationCheck,
    OperationCancelledError,
    cancellation_scope,
    raise_if_cancelled,
    report_progress,
)
from bdsubmerge.domain.models import BdmvLayout, PgStreamInfo, PlaylistInfo
from bdsubmerge.domain.timebase import MediaTick90k


class ParserFactory(Protocol):
    def __call__(self, path: str) -> object: ...


class PlaylistParser(Protocol):
    def parse(self, path: Path, layout: BdmvLayout) -> PlaylistInfo: ...


_MISSING = object()


def _member(value: object, *names: str, default: object = _MISSING) -> object:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return cast(Mapping[str, object], value)[name]
        if hasattr(value, name):
            return getattr(value, name)
    if default is not _MISSING:
        return default
    raise KeyError(f"Expected one of fields: {', '.join(names)}")


def _sequence(value: object, *names: str) -> tuple[object, ...]:
    candidate = _member(value, *names, default=())
    if candidate is None:
        return ()
    if isinstance(candidate, Mapping):
        return tuple(candidate.values())
    if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
        return tuple(candidate)
    raise TypeError(f"{names[0]} must be a sequence")


def _integer(value: object, *names: str, default: int | None = None) -> int:
    candidate = _member(value, *names, default=default)
    if candidate is None:
        raise KeyError(f"Expected integer field {names[0]}")
    if isinstance(candidate, bool):
        return int(candidate)
    return int(cast(Any, candidate))


def _text(value: object, *names: str, default: object = _MISSING) -> str:
    candidate = _member(value, *names, default=default)
    if isinstance(candidate, bytes):
        return candidate.decode("ascii")
    return str(candidate)


def _boolean(value: object, *names: str, default: bool = False) -> bool:
    candidate = _member(value, *names, default=default)
    return bool(candidate)


def _parser_data(parser: object) -> object:
    return _member(parser, "data", "Data", default=parser)


def _playlist_section(data: object) -> object:
    return _member(data, "PlayList", "playlist", default=data)


def _mark_section(data: object) -> object:
    return _member(data, "PlayListMark", "playlist_mark", "marks", default={})


def _pg_streams(play_item: object) -> tuple[PgStreamInfo, ...]:
    stn = _member(play_item, "STNTable", "stn_table", default={})
    entries = _sequence(
        stn,
        "PrimaryPGStreamEntries",
        "PrimaryPGStreams",
        "primary_pg_stream_entries",
    )
    streams: list[PgStreamInfo] = []
    for entry in entries:
        stream_entry = _member(entry, "StreamEntry", "stream_entry", default=entry)
        attributes = _member(entry, "StreamAttributes", "stream_attributes", default=entry)
        pid = _member(stream_entry, "RefToStreamPID", "ref_to_stream_pid", "pid", default=None)
        coding_type = _member(
            attributes,
            "StreamCodingType",
            "stream_coding_type",
            "coding_type",
            default=None,
        )
        language = _member(attributes, "LanguageCode", "language_code", "language", default=None)
        streams.append(
            PgStreamInfo(
                pid=int(cast(Any, pid)) if pid is not None else None,
                language=str(language) if language is not None else None,
                coding_type=cast(int | str | None, coding_type),
            )
        )
    return tuple(streams)


def _raw_item(value: object, selected_angle: int) -> RawPlayItem:
    is_multi_angle = _boolean(value, "IsMultiAngle", "is_multi_angle")
    angles = _sequence(value, "Angles", "angles")
    angle_count = _integer(
        value,
        "NumberOfAngles",
        "number_of_angles",
        default=(len(angles) + 1 if is_multi_angle else 1),
    )
    if selected_angle < 0 or selected_angle >= angle_count:
        raise ValueError(f"selected angle {selected_angle} outside 0..{angle_count - 1}")

    selected = value
    if selected_angle > 0:
        selected = angles[selected_angle - 1]
    return RawPlayItem(
        clip_id=_text(
            selected,
            "ClipInformationFileName",
            "clip_information_file_name",
            "clip_id",
        ),
        codec_id=_text(
            selected,
            "ClipCodecIdentifier",
            "clip_codec_identifier",
            "codec_id",
            default="M2TS",
        ),
        in_time_45k=_integer(value, "INTime", "in_time", "in_time_45k"),
        out_time_45k=_integer(value, "OUTTime", "out_time", "out_time_45k"),
        connection_condition=_integer(
            value,
            "ConnectionCondition",
            "connection_condition",
            default=0,
        ),
        is_multi_angle=is_multi_angle,
        selected_angle=selected_angle,
        angle_count=angle_count,
        primary_pg_streams=_pg_streams(value),
    )


def _raw_mark(value: object) -> RawPlaylistMark:
    duration = _member(value, "Duration", "duration", "duration_45k", default=None)
    pid = _member(value, "EntryESPID", "entry_es_pid", default=None)
    return RawPlaylistMark(
        mark_type=_integer(value, "MarkType", "mark_type", default=0),
        play_item_index=_integer(
            value,
            "RefToPlayItemID",
            "ref_to_play_item_id",
            "play_item_index",
        ),
        timestamp_45k=_integer(value, "MarkTimeStamp", "mark_time_stamp", "timestamp_45k"),
        entry_es_pid=int(cast(Any, pid)) if pid is not None else None,
        duration_45k=int(cast(Any, duration)) if duration is not None else None,
    )


def _default_factory(path: str) -> object:
    module = import_module("shinya.bd")
    movie_playlist_file = cast(ParserFactory, module.__dict__["MoviePlaylistFile"])
    return movie_playlist_file(path)


class ShinyaPlaylistAdapter:
    """Parse MPLS files while containing all Shinya-specific field knowledge."""

    def __init__(self, parser_factory: ParserFactory | None = None) -> None:
        self._parser_factory = parser_factory or _default_factory

    def parse(
        self,
        path: Path,
        layout: BdmvLayout,
        *,
        selected_angles: Mapping[int, int] | None = None,
    ) -> PlaylistInfo:
        raise_if_cancelled()
        parser = self._parser_factory(str(path))
        raise_if_cancelled()
        data = _parser_data(parser)
        playlist = _playlist_section(data)
        raw_items_list: list[RawPlayItem] = []
        for index, item in enumerate(
            _sequence(playlist, "PlayItems", "play_items", "PlayItem")
        ):
            raise_if_cancelled()
            raw_items_list.append(
                _raw_item(item, (selected_angles or {}).get(index, 0))
            )
        raw_items = tuple(raw_items_list)
        mark_section = _mark_section(data)
        raw_marks_list: list[RawPlaylistMark] = []
        for mark in _sequence(
            mark_section,
            "PlayListMarks",
            "PlaylistMarks",
            "playlist_marks",
            "marks",
        ):
            raise_if_cancelled()
            raw_marks_list.append(_raw_mark(mark))
        raw_marks = tuple(raw_marks_list)
        raise_if_cancelled()
        return build_playlist(
            path,
            raw_items,
            raw_marks,
            stream_path=layout.stream_path,
            clipinf_path=layout.clipinf_path,
        )


def _unavailable(path: Path, error: Exception) -> PlaylistInfo:
    return PlaylistInfo(
        path=path,
        stem=path.stem,
        duration_90k=MediaTick90k(0),
        play_items=(),
        marks=(),
        errors=(f"{type(error).__name__}: {error}",),
    )


def scan_playlists(
    layout: BdmvLayout,
    *,
    adapter: PlaylistParser | None = None,
    cancellation_check: CancellationCheck | None = None,
) -> tuple[PlaylistInfo, ...]:
    """Parse each MPLS independently so one malformed file cannot abort a scan."""
    raise_if_cancelled(cancellation_check)
    parser = adapter or ShinyaPlaylistAdapter()
    try:
        paths: list[Path] = []
        for path in layout.playlist_path.iterdir():
            raise_if_cancelled(cancellation_check)
            if path.is_file() and path.suffix.casefold() == ".mpls":
                paths.append(path)
        paths.sort(key=lambda path: path.name.casefold())
    except (OSError, PermissionError):
        return ()
    results: list[PlaylistInfo] = []
    path_count = len(paths)
    for index, path in enumerate(paths):
        raise_if_cancelled(cancellation_check)
        report_progress(15 + (index * 70 // path_count), str(path))
        try:
            with cancellation_scope(cancellation_check):
                results.append(parser.parse(path, layout))
        except OperationCancelledError:
            raise
        except Exception as error:
            results.append(_unavailable(path, error))
        raise_if_cancelled(cancellation_check)
    return tuple(results)
