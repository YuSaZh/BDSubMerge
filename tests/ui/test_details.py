from pathlib import Path

from bdsubmerge.application.display_models import (
    PgsSegmentDisplay,
    PlaylistMarkDisplay,
    PlaylistPgStreamDisplay,
    PlaylistPlayItemDisplay,
    PlaylistStructureDisplay,
    SubtitleDetailsDisplay,
    SubtitleSectionDisplay,
)
from bdsubmerge.ui.details import format_playlist_details, format_subtitle_details
from bdsubmerge.ui.translations import TranslationCatalog


def test_playlist_details_render_complete_projection_in_chinese() -> None:
    play_item = PlaylistPlayItemDisplay(
        0,
        "00010",
        "M2TS",
        45_000,
        135_000,
        0,
        180_000,
        180_000,
        5,
        True,
        1,
        2,
        True,
        False,
        (PlaylistPgStreamDisplay(0x1200, "jpn", 0x90),),
    )
    mark = PlaylistMarkDisplay(0, 1, 0, 67_500, 45_000, 0x1011, 4_500)
    details = PlaylistStructureDisplay(
        Path("BDMV/PLAYLIST/00010.mpls"),
        "00010",
        180_000,
        88,
        "high",
        True,
        1,
        1,
        125,
        True,
        False,
        (
            "Duration exceeds the main-feature threshold",
            "Repeated clip references reduce score by 7",
        ),
        (play_item,),
        (mark,),
        (("00010", 45_000, 135_000, 5),),
        ("PlayItem 0 missing CLIPINF/00010.clpi",),
        ("Playlist total duration is zero",),
    )

    rendered = format_playlist_details(details, TranslationCatalog().text)

    assert "重复片段比例: 12.5%" in rendered
    assert "片段=00010" in rendered
    assert "多角度=是" in rendered
    assert "PID=4608 语言=jpn" in rendered
    assert "章节标记（1）" in rendered  # noqa: RUF001
    assert "源时间（45 kHz）=67500" in rendered  # noqa: RUF001
    assert "时长（45 kHz）=4500" in rendered  # noqa: RUF001
    assert "时间线指纹（1）" in rendered  # noqa: RUF001
    assert "00010: 45000..135000，选中角度=5" in rendered  # noqa: RUF001
    assert "时长超过正片阈值" in rendered
    assert "重复片段引用使推荐分降低 7" in rendered
    assert "PlayItem 0 缺少 CLIPINF/00010.clpi" in rendered
    assert "播放列表总时长为零" in rendered
    assert "Duration exceeds" not in rendered


def test_subtitle_details_render_attachments_sections_and_pgs_segments() -> None:
    details = SubtitleDetailsDisplay(
        Path("subtitles/episode.sup"),
        "episode.sup",
        "sup",
        None,
        False,
        4,
        0,
        None,
        180_000,
        180_000,
        False,
        True,
        None,
        None,
        ("body.ttf",),
        ("logo.png",),
        True,
        1,
        (SubtitleSectionDisplay("Events", "events", 4),),
        4,
        (
            PgsSegmentDisplay(0x16, "presentation composition", 3),
            PgsSegmentDisplay(0x99, "unknown", 1),
        ),
        ("duration estimated",),
    )

    rendered = format_subtitle_details(details, TranslationCatalog().text)

    assert "文件名: episode.sup" in rendered
    assert "编码: 未知" in rendered
    assert "最早开始时间: 未知" in rendered
    assert "字体附件（1）\n  - body.ttf" in rendered  # noqa: RUF001
    assert "Aegisub Extradata: 是（1 条）" in rendered  # noqa: RUF001
    assert "0x16 呈现合成：3 个包" in rendered
    assert "0x99 未知：1 个包" in rendered
    assert "警告（1）" in rendered  # noqa: RUF001
