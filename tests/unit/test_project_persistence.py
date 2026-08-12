import json
from pathlib import Path

import pytest

from bdsubmerge.project.persistence import (
    dump_project_bytes,
    dumps_project,
    load_project_bytes,
    loads_project,
    save_project,
)
from bdsubmerge.project.schema import (
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


def sample_project() -> ProjectSnapshot:
    fingerprint = FileFingerprint(123, 456)
    index = FileSnapshot(StoredPath("disc/BDMV/index.bdmv", "D:/disc/BDMV/index.bdmv"), fingerprint)
    playlist_source = FileSnapshot(
        StoredPath("disc/BDMV/PLAYLIST/00001.mpls", "D:/disc/BDMV/PLAYLIST/00001.mpls"),
        FileFingerprint(200, 500),
    )
    subtitle_source = FileSnapshot(
        StoredPath("subs/E01.ass", "D:/subs/E01.ass"),
        FileFingerprint(300, 600),
    )
    boundaries = (
        BoundarySnapshot("start", 0, ("playlist_start",)),
        BoundarySnapshot(
            "end",
            90_000,
            ("chapter",),
            ("mark:1",),
            note="episode boundary",
        ),
    )
    return ProjectSnapshot(
        FileSnapshot(StoredPath("disc/BDMV", "D:/disc/BDMV"), FileFingerprint(4, 400)),
        index,
        PlaylistSnapshot(
            playlist_source,
            "00001",
            90_000,
            (("00001", 0, 45_000, 0),),
        ),
        (
            SubtitleSnapshot(
                "E01",
                subtitle_source,
                "ass",
                "utf-8-sig",
                0,
                89_000,
                88_000,
                12,
                2,
                (("language", "zh-CN"),),
                ("long tail",),
            ),
        ),
        boundaries,
        (MappingSnapshot("E01", "start", "end", 0, 90_000, 90, True, "high"),),
        (
            OutputSnapshot(
                "primary",
                "jriver",
                "",
                StoredPath("disc/BDMV/index.ass", "D:/disc/BDMV/index.ass"),
                "utf-8-sig",
                "abort",
            ),
        ),
        ConflictPolicySnapshot(accept_script_info_conflicts=True),
        "user note",
    )


def test_project_round_trip_preserves_reproducibility_state() -> None:
    project = sample_project()

    restored = loads_project(dumps_project(project))

    assert restored == project
    assert restored.mappings[0].locked is True
    assert restored.outputs[0].collision_policy == "abort"
    assert restored.playlist.timeline_fingerprint == (("00001", 0, 45_000, 0),)
    assert restored.bdmv.fingerprint == FileFingerprint(4, 400)
    assert restored.subtitles[0].metadata == (("language", "zh-CN"),)
    assert restored.boundaries[1].source_references == ("mark:1",)


def test_json_is_deterministic_utf8_without_bom() -> None:
    project = sample_project()

    first = dump_project_bytes(project)
    second = dump_project_bytes(project)

    assert first == second
    assert first.startswith(b"{\n")
    assert not first.startswith(b"\xef\xbb\xbf")
    assert load_project_bytes(first) == project


def test_save_delegates_bytes_to_injected_writer() -> None:
    calls: list[tuple[Path, bytes]] = []

    save_project(
        sample_project(),
        Path("show.bdsm.json"),
        writer=lambda path, data: calls.append((path, data)),
    )

    assert calls[0][0] == Path("show.bdsm.json")
    assert json.loads(calls[0][1])["schema_version"] == 1


def test_invalid_mapping_reference_is_rejected() -> None:
    payload = json.loads(dumps_project(sample_project()))
    payload["mappings"][0]["subtitle_id"] = "missing"

    with pytest.raises(ProjectSchemaError, match="unknown subtitle"):
        loads_project(json.dumps(payload))


def test_future_schema_is_rejected() -> None:
    payload = json.loads(dumps_project(sample_project()))
    payload["schema_version"] = 999

    with pytest.raises(ProjectSchemaError, match="newer than supported"):
        loads_project(json.dumps(payload))
