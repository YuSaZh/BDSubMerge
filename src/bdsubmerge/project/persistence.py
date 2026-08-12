"""Pure JSON codec and injected project-file persistence."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from .migration import JsonObject, migrate_payload
from .schema import (
    BoundarySnapshot,
    ConflictPolicySnapshot,
    FileFingerprint,
    FileSnapshot,
    MappingSnapshot,
    OutputSnapshot,
    PlaylistSnapshot,
    ProjectSchemaError,
    ProjectSnapshot,
    StoredPath,
    SubtitleSnapshot,
)

type ProjectWriter = Callable[[Path, bytes], None]


def _stored_path_to_data(value: StoredPath) -> JsonObject:
    return {"relative": value.relative, "absolute": value.absolute}


def _fingerprint_to_data(value: FileFingerprint) -> JsonObject:
    return {"size": value.size, "mtime_ns": value.mtime_ns}


def _file_to_data(value: FileSnapshot) -> JsonObject:
    return {
        "path": _stored_path_to_data(value.path),
        "fingerprint": _fingerprint_to_data(value.fingerprint),
    }


def project_to_data(project: ProjectSnapshot) -> JsonObject:
    """Convert a project to JSON primitives with stable field names."""

    return {
        "schema_version": project.schema_version,
        "bdmv": _file_to_data(project.bdmv),
        "index_bdmv": _file_to_data(project.index_bdmv),
        "playlist": {
            "source": _file_to_data(project.playlist.source),
            "stem": project.playlist.stem,
            "duration_90k": project.playlist.duration_90k,
            "timeline_fingerprint": [list(item) for item in project.playlist.timeline_fingerprint],
        },
        "subtitles": [
            {
                "id": item.id,
                "source": _file_to_data(item.source),
                "format": item.format,
                "encoding": item.encoding,
                "order": item.order,
                "raw_end_90k": item.raw_end_90k,
                "effective_end_90k": item.effective_end_90k,
                "event_count": item.event_count,
                "style_count": item.style_count,
                "metadata": [list(value) for value in item.metadata],
                "warnings": list(item.warnings),
            }
            for item in project.subtitles
        ],
        "boundaries": [
            {
                "id": item.id,
                "time_90k": item.time_90k,
                "kinds": list(item.kinds),
                "source_references": list(item.source_references),
                "confidence": item.confidence,
                "enabled": item.enabled,
                "user_created": item.user_created,
                "note": item.note,
            }
            for item in project.boundaries
        ],
        "mappings": [
            {
                "subtitle_id": item.subtitle_id,
                "start_boundary_id": item.start_boundary_id,
                "end_boundary_id": item.end_boundary_id,
                "start_90k": item.start_90k,
                "end_90k": item.end_90k,
                "manual_offset_90k": item.manual_offset_90k,
                "locked": item.locked,
                "confidence": item.confidence,
                "warnings": list(item.warnings),
            }
            for item in project.mappings
        ],
        "outputs": [
            {
                "id": item.id,
                "preset": item.preset,
                "path_template": item.path_template,
                "resolved_path": (
                    _stored_path_to_data(item.resolved_path)
                    if item.resolved_path is not None
                    else None
                ),
                "encoding": item.encoding,
                "collision_policy": item.collision_policy,
                "backup_policy": item.backup_policy,
            }
            for item in project.outputs
        ],
        "conflict_policy": {
            "accept_script_info_conflicts": (
                project.conflict_policy.accept_script_info_conflicts
            ),
            "keep_events_ending_before_zero": (
                project.conflict_policy.keep_events_ending_before_zero
            ),
            "clip_negative_starts": project.conflict_policy.clip_negative_starts,
            "preserve_unknown_sections": project.conflict_policy.preserve_unknown_sections,
        },
        "ui_notes": project.ui_notes,
    }


def dumps_project(project: ProjectSnapshot, *, indent: int = 2) -> str:
    return json.dumps(
        project_to_data(project),
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
    ) + "\n"


def dump_project_bytes(project: ProjectSnapshot) -> bytes:
    return dumps_project(project).encode("utf-8")


def save_project(project: ProjectSnapshot, path: Path, *, writer: ProjectWriter) -> None:
    """Serialize and delegate the actual write to an injected atomic writer."""

    writer(path, dump_project_bytes(project))


def loads_project(text: str) -> ProjectSnapshot:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProjectSchemaError(f"invalid project JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise ProjectSchemaError("project JSON root must be an object")
    return project_from_data(migrate_payload(cast(JsonObject, value)))


def load_project_bytes(data: bytes) -> ProjectSnapshot:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ProjectSchemaError("project file must be UTF-8") from error
    return loads_project(text)


def project_from_data(data: JsonObject) -> ProjectSnapshot:
    """Validate JSON primitives and construct the controlled schema model."""

    try:
        bdmv = _file_snapshot(_object(data, "bdmv"))
        index_bdmv = _file_snapshot(_object(data, "index_bdmv"))
        playlist_data = _object(data, "playlist")
        playlist = PlaylistSnapshot(
            _file_snapshot(_object(playlist_data, "source")),
            _string(playlist_data, "stem"),
            _integer(playlist_data, "duration_90k"),
            tuple(_timeline_item(item) for item in _array(playlist_data, "timeline_fingerprint")),
        )
        subtitles = tuple(_subtitle(item) for item in _object_array(data, "subtitles"))
        boundaries = tuple(_boundary(item) for item in _object_array(data, "boundaries"))
        mappings = tuple(_mapping(item) for item in _object_array(data, "mappings"))
        outputs = tuple(_output(item) for item in _object_array(data, "outputs"))
        policy_data = _object(data, "conflict_policy")
        policy = ConflictPolicySnapshot(
            _boolean_default(policy_data, "accept_script_info_conflicts", False),
            _boolean_default(policy_data, "keep_events_ending_before_zero", False),
            _boolean_default(policy_data, "clip_negative_starts", True),
            _boolean_default(policy_data, "preserve_unknown_sections", True),
        )
        return ProjectSnapshot(
            bdmv,
            index_bdmv,
            playlist,
            subtitles,
            boundaries,
            mappings,
            outputs,
            policy,
            _string_default(data, "ui_notes", ""),
            _integer(data, "schema_version"),
        )
    except (KeyError, TypeError) as error:
        raise ProjectSchemaError(f"invalid project structure: {error}") from error


def _stored_path(data: JsonObject) -> StoredPath:
    relative = data.get("relative")
    if relative is not None and not isinstance(relative, str):
        raise ProjectSchemaError("path relative value must be a string or null")
    return StoredPath(relative, _string(data, "absolute"))


def _fingerprint(data: JsonObject) -> FileFingerprint:
    return FileFingerprint(_integer(data, "size"), _integer(data, "mtime_ns"))


def _file_snapshot(data: JsonObject) -> FileSnapshot:
    return FileSnapshot(
        _stored_path(_object(data, "path")),
        _fingerprint(_object(data, "fingerprint")),
    )


def _subtitle(data: JsonObject) -> SubtitleSnapshot:
    return SubtitleSnapshot(
        _string(data, "id"),
        _file_snapshot(_object(data, "source")),
        _string(data, "format"),
        _string(data, "encoding"),
        _integer(data, "order"),
        _optional_integer(data, "raw_end_90k"),
        _optional_integer(data, "effective_end_90k"),
        _integer_default(data, "event_count", 0),
        _integer_default(data, "style_count", 0),
        tuple(_metadata_item(value) for value in _array_default(data, "metadata")),
        _string_tuple_default(data, "warnings"),
    )


def _boundary(data: JsonObject) -> BoundarySnapshot:
    return BoundarySnapshot(
        _string(data, "id"),
        _integer(data, "time_90k"),
        _string_tuple(data, "kinds"),
        _string_tuple_default(data, "source_references"),
        _integer_default(data, "confidence", 100),
        _boolean_default(data, "enabled", True),
        _boolean_default(data, "user_created", False),
        _string_default(data, "note", ""),
    )


def _mapping(data: JsonObject) -> MappingSnapshot:
    return MappingSnapshot(
        _string(data, "subtitle_id"),
        _string(data, "start_boundary_id"),
        _string(data, "end_boundary_id"),
        _integer(data, "start_90k"),
        _integer(data, "end_90k"),
        _integer_default(data, "manual_offset_90k", 0),
        _boolean_default(data, "locked", False),
        _string_default(data, "confidence", "low"),
        _string_tuple(data, "warnings"),
    )


def _output(data: JsonObject) -> OutputSnapshot:
    resolved = data.get("resolved_path")
    if resolved is not None and not isinstance(resolved, dict):
        raise ProjectSchemaError("resolved output path must be an object or null")
    return OutputSnapshot(
        _string(data, "id"),
        _string(data, "preset"),
        _string_default(data, "path_template", ""),
        _stored_path(resolved) if resolved is not None else None,
        _string(data, "encoding"),
        _string(data, "collision_policy"),
        _string_default(data, "backup_policy", "none"),
    )


def _timeline_item(value: Any) -> tuple[str, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise ProjectSchemaError("timeline fingerprint item must contain four values")
    clip = value[0]
    first, second, third = value[1], value[2], value[3]
    if (
        not isinstance(clip, str)
        or not isinstance(first, int)
        or isinstance(first, bool)
        or not isinstance(second, int)
        or isinstance(second, bool)
        or not isinstance(third, int)
        or isinstance(third, bool)
    ):
        raise ProjectSchemaError("timeline fingerprint values have invalid types")
    return clip, first, second, third


def _metadata_item(value: Any) -> tuple[str, str]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not isinstance(value[0], str)
        or not isinstance(value[1], str)
    ):
        raise ProjectSchemaError("subtitle metadata item must contain two strings")
    key = value[0]
    metadata_value = value[1]
    return key, metadata_value


def _object(data: JsonObject, key: str) -> JsonObject:
    value = data[key]
    if not isinstance(value, dict):
        raise ProjectSchemaError(f"{key} must be an object")
    return cast(JsonObject, value)


def _array(data: JsonObject, key: str) -> list[Any]:
    value = data[key]
    if not isinstance(value, list):
        raise ProjectSchemaError(f"{key} must be an array")
    return value


def _array_default(data: JsonObject, key: str) -> list[Any]:
    return _array(data, key) if key in data else []


def _object_array(data: JsonObject, key: str) -> tuple[JsonObject, ...]:
    values = _array(data, key)
    result: list[JsonObject] = []
    for value in values:
        if not isinstance(value, dict):
            raise ProjectSchemaError(f"{key} must contain only objects")
        result.append(cast(JsonObject, value))
    return tuple(result)


def _string(data: JsonObject, key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ProjectSchemaError(f"{key} must be a string")
    return value


def _string_default(data: JsonObject, key: str, default: str) -> str:
    return _string(data, key) if key in data else default


def _integer(data: JsonObject, key: str) -> int:
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProjectSchemaError(f"{key} must be an integer")
    return value


def _integer_default(data: JsonObject, key: str, default: int) -> int:
    return _integer(data, key) if key in data else default


def _optional_integer(data: JsonObject, key: str) -> int | None:
    return None if data.get(key) is None else _integer(data, key)


def _boolean_default(data: JsonObject, key: str, default: bool) -> bool:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, bool):
        raise ProjectSchemaError(f"{key} must be a boolean")
    return value


def _string_tuple(data: JsonObject, key: str) -> tuple[str, ...]:
    values = _array(data, key)
    if any(not isinstance(value, str) for value in values):
        raise ProjectSchemaError(f"{key} must contain only strings")
    return tuple(cast(str, value) for value in values)


def _string_tuple_default(data: JsonObject, key: str) -> tuple[str, ...]:
    return _string_tuple(data, key) if key in data else ()
