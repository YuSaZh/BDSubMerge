from pathlib import Path

from bdsubmerge.output import (
    CollisionPolicy,
    FullPathOutputTarget,
    JRiverOutputTarget,
    OutputContext,
    preflight_outputs,
)


def test_any_collision_blocks_the_whole_preflight(tmp_path: Path) -> None:
    first = tmp_path / "one.ass"
    first.write_text("existing", encoding="utf-8")
    context = OutputContext(subtitle_format="ass")
    targets = (
        FullPathOutputTarget("one", path=first),
        FullPathOutputTarget("two", path=tmp_path / "two.ass"),
    )

    result = preflight_outputs(targets, context)

    assert result.ready is False
    assert [issue.code for issue in result.errors] == ["destination_exists"]
    assert not (tmp_path / "two.ass").exists()


def test_multiple_targets_may_not_resolve_to_same_path(tmp_path: Path) -> None:
    path = tmp_path / "index.ass"
    targets = (
        FullPathOutputTarget("first", path=path),
        FullPathOutputTarget("second", path=path),
    )

    result = preflight_outputs(targets, OutputContext(subtitle_format="ass"))

    assert "outputs_overlap" in {issue.code for issue in result.errors}


def test_output_may_not_overwrite_an_input_subtitle(tmp_path: Path) -> None:
    input_path = tmp_path / "episode.ass"
    input_path.write_text("source", encoding="utf-8")
    context = OutputContext(subtitle_format="ass", input_subtitle_paths=(input_path,))

    result = preflight_outputs(
        (FullPathOutputTarget("same", CollisionPolicy.OVERWRITE, path=input_path),), context
    )

    assert "overwrites_input" in {issue.code for issue in result.errors}


def test_existing_directory_cannot_be_used_as_an_output_destination(tmp_path: Path) -> None:
    destination = tmp_path / "episode.ass"
    destination.mkdir()

    result = preflight_outputs(
        (
            FullPathOutputTarget(
                "target",
                CollisionPolicy.BACKUP,
                path=destination,
            ),
        ),
        OutputContext(subtitle_format="ass"),
    )

    assert result.ready is False
    assert "invalid_output_destination" in {issue.code for issue in result.errors}
    assert destination.is_dir()


def test_jriver_preflight_requires_real_index_and_exact_destination(tmp_path: Path) -> None:
    index_path = tmp_path / "BDMV" / "index.bdmv"
    index_path.parent.mkdir()
    index_path.write_bytes(b"index")
    context = OutputContext(subtitle_format="ass", index_bdmv_path=index_path)

    result = preflight_outputs((JRiverOutputTarget("jriver"),), context)

    assert result.ready is True
    assert result.outputs[0].path == index_path.with_suffix(".ass")


def test_backup_preflight_selects_non_colliding_backup_name(tmp_path: Path) -> None:
    destination = tmp_path / "output.srt"
    destination.write_text("old", encoding="utf-8")
    (tmp_path / "output.srt.bak").write_text("older", encoding="utf-8")
    target = FullPathOutputTarget("target", CollisionPolicy.BACKUP, path=destination)

    result = preflight_outputs((target,), OutputContext(subtitle_format="srt"))

    assert result.ready is True
    assert result.outputs[0].backup_path == tmp_path / "output.srt.bak.1"
