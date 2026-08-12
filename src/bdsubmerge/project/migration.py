"""Ordered project-schema migrations."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from .schema import CURRENT_SCHEMA_VERSION, ProjectSchemaError

type JsonObject = dict[str, Any]
type Migration = Callable[[JsonObject], JsonObject]


def _v0_to_v1(payload: JsonObject) -> JsonObject:
    migrated = deepcopy(payload)
    migrated.pop("version", None)
    if "notes" in migrated and "ui_notes" not in migrated:
        migrated["ui_notes"] = migrated.pop("notes")
    migrated.setdefault("boundaries", [])
    migrated.setdefault("mappings", [])
    migrated.setdefault("outputs", [])
    migrated.setdefault("subtitles", [])
    migrated.setdefault("conflict_policy", {})
    migrated.setdefault("ui_notes", "")
    migrated["schema_version"] = 1
    return migrated


_MIGRATIONS: dict[int, Migration] = {0: _v0_to_v1}


def migrate_payload(payload: JsonObject) -> JsonObject:
    """Return a current-schema copy, applying each registered migration in order."""

    migrated = deepcopy(payload)
    version_value = migrated.get("schema_version", migrated.get("version", 0))
    if not isinstance(version_value, int) or isinstance(version_value, bool):
        raise ProjectSchemaError("schema_version must be an integer")
    if version_value > CURRENT_SCHEMA_VERSION:
        raise ProjectSchemaError(
            f"project schema {version_value} is newer than supported "
            f"schema {CURRENT_SCHEMA_VERSION}"
        )
    version = version_value
    while version < CURRENT_SCHEMA_VERSION:
        migration = _MIGRATIONS.get(version)
        if migration is None:
            raise ProjectSchemaError(f"no migration is registered for schema {version}")
        migrated = migration(migrated)
        new_version = migrated.get("schema_version")
        if new_version != version + 1:
            raise ProjectSchemaError(
                f"migration for schema {version} did not produce schema {version + 1}"
            )
        version += 1
    return _normalize_v1(migrated)


def _normalize_v1(payload: JsonObject) -> JsonObject:
    """Normalize early v1 drafts without pretending a missing fingerprint is valid."""

    normalized = deepcopy(payload)
    if "bdmv" not in normalized and "bdmv_path" in normalized:
        normalized["bdmv"] = {
            "path": normalized.pop("bdmv_path"),
            "fingerprint": {"size": 0, "mtime_ns": 0},
        }
    return normalized
