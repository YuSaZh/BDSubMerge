from pathlib import Path

from bdsubmerge.application.display_models import (
    build_playlist_structure,
    build_subtitle_details,
    format_playlist_structure,
    format_subtitle_details,
    format_ticks_90k,
)
from bdsubmerge.application.models import SubtitleAsset
from bdsubmerge.domain.models import (
    PgStreamInfo,
    PlayItemInfo,
    PlaylistConfidence,
    PlaylistInfo,
    PlaylistMarkInfo,
    ReferenceStatus,
)
from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.subtitles import (
    PgsDocument,
    PgsPacket,
    PgsSegmentType,
    SubtitleFormat,
    TextSubtitleInfo,
    parse_ass,
    parse_srt,
)


def test_playlist_structure_projects_complete_read_only_parse_information() -> None:
    first_item = PlayItemInfo(
        index=0,
        clip_id="00001",
        codec_id="M2TS",
        in_time_45k=45_000,
        out_time_45k=135_000,
        logical_start_90k=MediaTick90k(0),
        logical_end_90k=MediaTick90k(180_000),
        connection_condition=5,
        is_multi_angle=True,
        selected_angle=1,
        angle_count=2,
        references=ReferenceStatus(True, False),
        primary_pg_streams=(PgStreamInfo(0x1200, "jpn", 0x90),),
    )
    second_item = PlayItemInfo(
        index=1,
        clip_id="00001",
        codec_id="M2TS",
        in_time_45k=0,
        out_time_45k=45_000,
        logical_start_90k=MediaTick90k(180_000),
        logical_end_90k=MediaTick90k(270_000),
        connection_condition=1,
        is_multi_angle=False,
        selected_angle=0,
        angle_count=1,
        references=ReferenceStatus(True, True),
    )
    mark = PlaylistMarkInfo(
        index=0,
        mark_type=1,
        play_item_index=1,
        timestamp_45k=22_500,
        time_90k=MediaTick90k(225_000),
        entry_es_pid=0x1011,
        duration_45k=4_500,
    )
    playlist = PlaylistInfo(
        path=Path("BDMV/PLAYLIST/00010.mpls"),
        stem="00010",
        duration_90k=MediaTick90k(270_000),
        play_items=(first_item, second_item),
        marks=(mark,),
        warnings=("missing CLPI reference",),
        score=88,
        confidence=PlaylistConfidence.HIGH,
        recommendation_reasons=("feature-length timeline",),
        timeline_fingerprint=(("00001", 45_000, 135_000, 5),),
    )

    details = build_playlist_structure(playlist)

    assert details.path == playlist.path
    assert details.duration_90k == 270_000
    assert details.unique_clip_count == 1
    assert details.repeated_clip_count == 1
    assert details.repeated_clip_ratio_per_mille == 500
    assert details.has_multi_angle is True
    assert details.references_complete is False
    assert details.play_items[0].primary_pg_streams[0].language == "jpn"
    assert details.play_items[0].duration_90k == 180_000
    assert details.marks[0].time_90k == 225_000

    rendered = format_playlist_structure(details)
    assert "Playlist: 00010" in rendered
    assert "Duration: 00:00:03.000 (270000 ticks)" in rendered
    assert "pid=4608 language=jpn coding_type=144" in rendered
    assert "[0] type=1 play_item=1" in rendered
    assert "missing CLPI reference" in rendered


def test_ass_source_details_include_analysis_sections_attachments_and_extradata() -> None:
    document = parse_ass(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
        "[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text, Extra\n"
        "Dialogue: 0:00:01.00,0:00:03.00,Default,line,0\n"
        "[Fonts]\nfontname: body.ttf\nencoded-font\n"
        "[Graphics]\nfilename: logo.png\nencoded-graphic\n"
        "[Aegisub Extradata]\nData: 0,key,value\n"
    )
    analysis = TextSubtitleInfo(
        event_count=1,
        style_count=1,
        earliest_start_ticks=90_000,
        raw_end_ticks=270_000,
        effective_end_ticks=270_000,
        suspected_long_tail=True,
        play_res_x=1920,
        play_res_y=1080,
    )
    asset = SubtitleAsset(
        Path("subtitles/episode.ass"),
        SubtitleFormat.ASS,
        document,
        analysis,
        "utf-8",
        True,
    )

    details = build_subtitle_details(asset, warnings=("long-tail event excluded",))

    assert details.filename == "episode.ass"
    assert details.font_attachment_names == ("body.ttf",)
    assert details.graphic_attachment_names == ("logo.png",)
    assert details.has_font_attachments is True
    assert details.has_graphic_attachments is True
    assert details.has_aegisub_extradata is True
    assert details.aegisub_extradata_entry_count == 1
    assert tuple(section.normalized_name for section in details.sections) == (
        "script info",
        "v4+ styles",
        "events",
        "fonts",
        "graphics",
        "aegisub extradata",
    )
    assert details.warning_count == 1

    rendered = format_subtitle_details(details)
    assert "Format: ass" in rendered
    assert "PlayRes: 1920x1080" in rendered
    assert "Font attachments (1):\n  - body.ttf" in rendered
    assert "Aegisub Extradata: yes (1 entries)" in rendered
    assert "Warnings (1):\n  - long-tail event excluded" in rendered


def test_srt_source_details_have_no_ass_or_pgs_structure() -> None:
    document = parse_srt("1\n00:00:00,000 --> 00:00:01,000\nline\n")
    asset = SubtitleAsset(
        Path("episode.srt"),
        SubtitleFormat.SRT,
        document,
        TextSubtitleInfo(1, 0, 0, 90_000, 90_000, False),
        "utf-8",
    )

    details = build_subtitle_details(asset)

    assert details.sections == ()
    assert details.font_attachment_names == ()
    assert details.graphic_attachment_names == ()
    assert details.has_aegisub_extradata is False
    assert details.pgs_packet_count == 0
    assert details.pgs_segments == ()


def test_empty_aegisub_extradata_section_is_still_reported_as_present() -> None:
    document = parse_ass(
        "[Script Info]\n"
        "[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:01.00,Default,line\n"
        "[Aegisub Extradata]\n"
    )
    asset = SubtitleAsset(
        Path("episode.ass"),
        SubtitleFormat.ASS,
        document,
        TextSubtitleInfo(1, 1, 0, 90_000, 90_000, False),
        "utf-8",
    )

    details = build_subtitle_details(asset)

    assert details.has_aegisub_extradata is True
    assert details.aegisub_extradata_entry_count == 0


def test_sup_source_details_summarize_segments_and_deduplicate_warnings() -> None:
    document = PgsDocument(
        (
            PgsPacket(
                MediaTick90k(90_000),
                MediaTick90k(80_000),
                PgsSegmentType.PRESENTATION_COMPOSITION,
                b"payload",
            ),
            PgsPacket(
                MediaTick90k(90_000),
                MediaTick90k(80_000),
                PgsSegmentType.OBJECT_DEFINITION,
                b"object",
            ),
            PgsPacket(
                MediaTick90k(180_000),
                MediaTick90k(0),
                PgsSegmentType.PRESENTATION_COMPOSITION,
                b"clear",
            ),
            PgsPacket(MediaTick90k(180_000), MediaTick90k(0), 0x99, b"unknown"),
        ),
        ("unsupported segment type",),
    )
    analysis = TextSubtitleInfo(
        event_count=4,
        style_count=0,
        earliest_start_ticks=90_000,
        raw_end_ticks=180_000,
        effective_end_ticks=180_000,
        suspected_long_tail=False,
        duration_estimated=True,
    )
    asset = SubtitleAsset(Path("episode.sup"), SubtitleFormat.SUP, document, analysis)

    details = build_subtitle_details(
        asset,
        warnings=("duration estimated", "unsupported segment type"),
    )

    assert details.encoding is None
    assert details.pgs_packet_count == 4
    assert tuple(
        (segment.segment_type, segment.name, segment.packet_count)
        for segment in details.pgs_segments
    ) == (
        (0x15, "object definition", 1),
        (0x16, "presentation composition", 2),
        (0x99, "unknown", 1),
    )
    assert details.warnings == ("duration estimated", "unsupported segment type")
    assert details.warning_count == 2

    rendered = format_subtitle_details(details)
    assert "Encoding: unknown" in rendered
    assert "Duration estimated: yes" in rendered
    assert "PGS packets: 4" in rendered
    assert "0x16 presentation composition: 2 packets" in rendered
    assert "0x99 unknown: 1 packets" in rendered


def test_tick_formatter_uses_integer_arithmetic_and_preserves_exact_ticks() -> None:
    assert format_ticks_90k(None) == "unknown"
    assert format_ticks_90k(135_000) == "00:00:01.500 (135000 ticks)"
    assert format_ticks_90k(1) == "00:00:00.000 (1 ticks)"
    assert format_ticks_90k(-90) == "-00:00:00.001 (-90 ticks)"
