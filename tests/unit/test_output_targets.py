from pathlib import Path

import pytest

from bdsubmerge.output import (
    CollisionPolicy,
    FullPathOutputTarget,
    JRiverOutputTarget,
    OutputContext,
    PlaylistOutputTarget,
    TemplateOutputTarget,
)


def test_jriver_path_is_exact_sibling_of_discovered_index() -> None:
    context = OutputContext(
        subtitle_format="ASS",
        index_bdmv_path=Path(r"D:\Anime\Title\BDMV\index.bdmv"),
    )
    target = JRiverOutputTarget("jriver")

    assert target.resolve_path(context) == Path(r"D:\Anime\Title\BDMV\index.ass")


def test_jriver_rejects_automatic_rename() -> None:
    context = OutputContext(
        subtitle_format="ass",
        index_bdmv_path=Path(r"D:\Anime\Title\BDMV\index.bdmv"),
    )
    target = JRiverOutputTarget("jriver", CollisionPolicy.AUTO_RENAME)

    assert target.validate(context) == ("JRiver output cannot use automatic renaming",)


def test_playlist_path_can_include_language_suffix(tmp_path: Path) -> None:
    context = OutputContext(
        subtitle_format="srt",
        playlist_path=tmp_path / "BDMV" / "PLAYLIST" / "00000.mpls",
        language="zh-Hans",
    )
    target = PlaylistOutputTarget("playlist", language_suffix=True)

    assert target.resolve_path(context).name == "00000.zh-Hans.srt"


def test_custom_template_expands_only_documented_variables(tmp_path: Path) -> None:
    context = OutputContext(
        subtitle_format="ass",
        playlist_path=tmp_path / "BDMV" / "PLAYLIST" / "00000.mpls",
        disc_container_path=tmp_path / "My Disc",
        language="zh-Hans",
    )
    target = TemplateOutputTarget(
        "custom",
        directory=tmp_path,
        template="{disc_name}_{playlist_stem}_{language}.{format}",
    )

    assert target.resolve_path(context) == tmp_path / "My Disc_00000_zh-Hans.ass"

    invalid = TemplateOutputTarget("invalid", directory=tmp_path, template="{unknown}.ass")
    with pytest.raises(ValueError, match="unknown output template"):
        invalid.resolve_path(context)


def test_full_path_is_not_rewritten() -> None:
    selected = Path(r"\\hpserver\storage\Anime\Title\custom.ass")
    target = FullPathOutputTarget("full", path=selected)

    assert target.resolve_path(OutputContext(subtitle_format="ass")) == selected
