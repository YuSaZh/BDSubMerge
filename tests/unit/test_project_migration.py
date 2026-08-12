from copy import deepcopy

from bdsubmerge.project.migration import migrate_payload
from bdsubmerge.project.persistence import project_to_data
from test_project_persistence import sample_project


def test_v0_migration_is_ordered_and_does_not_mutate_input() -> None:
    current = project_to_data(sample_project())
    current.pop("schema_version")
    current["version"] = 0
    current["notes"] = current.pop("ui_notes")
    original = deepcopy(current)

    migrated = migrate_payload(current)

    assert current == original
    assert migrated["schema_version"] == 1
    assert migrated["ui_notes"] == "user note"
    assert "version" not in migrated
    assert "notes" not in migrated


def test_current_payload_is_copied_without_changes() -> None:
    current = project_to_data(sample_project())

    migrated = migrate_payload(current)

    assert migrated == current
    assert migrated is not current


def test_early_v1_bdmv_path_is_normalized_with_untrusted_fingerprint() -> None:
    current = project_to_data(sample_project())
    bdmv = current.pop("bdmv")
    current["bdmv_path"] = bdmv["path"]

    migrated = migrate_payload(current)

    assert migrated["bdmv"]["path"] == bdmv["path"]
    assert migrated["bdmv"]["fingerprint"] == {"size": 0, "mtime_ns": 0}
    assert "bdmv_path" not in migrated
