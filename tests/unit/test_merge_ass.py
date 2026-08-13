import pytest

from bdsubmerge.merge.engine import MergeConflictError, merge_ass
from bdsubmerge.merge.plan import MergeOptions, MergePlan, MergeSource
from bdsubmerge.subtitles.ass_document import AssDocument, parse_ass


def _ass(*, color: str, play_res_x: int = 1920, extra: str = "") -> AssDocument:
    return parse_ass(
        f"[Script Info]\nPlayResX: {play_res_x}\nPlayResY: 1080\nWrapStyle: 0\n"
        "[V4+ Styles]\nFormat: Name, Fontname, PrimaryColour\n"
        f"Style: Default,Arial,{color}\n"
        "[Events]\nFormat: Text, Style, End, Start, Layer\n"
        f"Dialogue: {{\\rDefault}}line,Default,0:00:01.00,0:00:00.00,1\n{extra}"
        "[Custom]\nOpaque: yes\n"
    )


def test_ass_merge_keeps_source_order_shifts_comments_and_renames_styles() -> None:
    first = _ass(color="white")
    second = _ass(
        color="yellow",
        extra="Comment: note,Default,0:00:02.00,0:00:01.50,0\n",
    )
    plan = MergePlan(
        (
            MergeSource("E01", first, 0),
            MergeSource("E02", second, 9_000_000),
        )
    )

    result = merge_ass(plan)

    assert [event.kind for event in result.document.events] == ["Dialogue", "Dialogue", "Comment"]
    assert result.document.events[1].start_ticks == 9_000_000
    assert result.document.events[1].value("Style") == "Default__E02"
    assert result.document.events[1].value("Text") == r"{\rDefault__E02}line"
    assert result.report.output_event_count == 3
    assert result.report.style_renames[0].new_name == "Default__E02"


def test_script_resolution_conflict_requires_explicit_acceptance() -> None:
    plan = MergePlan(
        (
            MergeSource("E01", _ass(color="white"), 0),
            MergeSource("E02", _ass(color="white", play_res_x=1280), 1),
        )
    )

    with pytest.raises(MergeConflictError, match="Script Info conflict"):
        merge_ass(plan)

    accepted = merge_ass(
        MergePlan(plan.sources, MergeOptions(accept_script_info_conflicts=True))
    )
    assert accepted.report.errors[0].code == "script_info_conflict"


def test_negative_time_policy_drops_and_clips_with_report() -> None:
    document = parse_ass(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
        "[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:00:00.50,Default,dropped\n"
        "Dialogue: 0:00:00.40,0:00:01.50,Default,clipped\n"
    )
    result = merge_ass(MergePlan((MergeSource("E01", document, -45_000),)))

    assert len(result.document.events) == 1
    assert result.document.events[0].start_ticks == 0
    assert result.report.dropped_event_count == 1
    assert result.report.clipped_event_count == 1


def test_unknown_section_conflict_is_preserved_and_reported() -> None:
    first = _ass(color="white")
    second = parse_ass(_ass(color="white").serialize().replace("Opaque: yes", "Opaque: no"))

    result = merge_ass(
        MergePlan((MergeSource("E01", first, 0), MergeSource("E02", second, 90_000)))
    )

    assert len([section for section in result.document.sections if section.name == "Custom"]) == 2
    assert any(notice.code == "unknown_section_conflict" for notice in result.report.notices)


def test_karaoke_tags_and_vector_drawing_survive_time_shift() -> None:
    text = r"{\k20\kf30\ko10}歌{\p1}m 0 0 l 100 0 100 100{\p0}"
    document = parse_ass(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
        "[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Layer, Start, End, Style, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:01.00,Default,{text}\n"
    )

    result = merge_ass(MergePlan((MergeSource("E01", document, 90_000),)))

    event = result.document.events[0]
    assert event.start_ticks == 90_000
    assert event.end_ticks == 180_000
    assert event.value("Text") == text
    assert text in result.document.serialize()


def _ass_with_extradata(data_id: int, content: str) -> AssDocument:
    return parse_ass(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
        "[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Layer, Start, End, Style, Text, Extra\n"
        f"Dialogue: 0,0:00:00.00,0:00:01.00,Default,line,{data_id}\n"
        "[Aegisub Extradata]\n"
        f"Data: {data_id},{content}\n"
    )


def test_extradata_content_is_deduplicated_and_conflicting_id_is_remapped() -> None:
    result = merge_ass(
        MergePlan(
            (
                MergeSource("E01", _ass_with_extradata(0, "same"), 0),
                MergeSource("E02", _ass_with_extradata(7, "same"), 90_000),
                MergeSource("E03", _ass_with_extradata(0, "different"), 180_000),
            )
        )
    )

    extradata = result.document.section("Aegisub Extradata")
    assert extradata is not None
    assert extradata.serialize_lines() == (
        "[Aegisub Extradata]",
        "Data: 0,same",
        "Data: 1,different",
    )
    assert [event.value("Extra") for event in result.document.events] == ["0", "0", "1"]
    remaps = [notice for notice in result.report.notices if notice.code == "extradata_id_remapped"]
    assert [(notice.source_label, notice.message) for notice in remaps] == [
        ("E03", "Extradata ID 0 remapped to 1")
    ]


def _ass_with_attachments(*, font_data: str, graphic_data: str) -> AssDocument:
    return parse_ass(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
        "[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Layer, Start, End, Style, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,line\n"
        "[Fonts]\nfontname: shared.ttf\n"
        f"{font_data}\n"
        "[Graphics]\nfilename: shared.png\n"
        f"{graphic_data}\n"
    )


def test_font_and_graphic_attachments_deduplicate_and_rename_conflicts() -> None:
    result = merge_ass(
        MergePlan(
            (
                MergeSource(
                    "E01",
                    _ass_with_attachments(font_data="font-a", graphic_data="graphic-a"),
                    0,
                ),
                MergeSource(
                    "E02",
                    _ass_with_attachments(font_data="font-a", graphic_data="graphic-b"),
                    90_000,
                ),
                MergeSource(
                    "E03",
                    _ass_with_attachments(font_data="font-b", graphic_data="graphic-a"),
                    180_000,
                ),
            )
        )
    )

    fonts = result.document.section("Fonts")
    graphics = result.document.section("Graphics")
    assert fonts is not None
    assert graphics is not None
    assert fonts.serialize_lines() == (
        "[Fonts]",
        "fontname: shared.ttf",
        "font-a",
        "fontname: shared.ttf__E03",
        "font-b",
    )
    assert graphics.serialize_lines() == (
        "[Graphics]",
        "filename: shared.png",
        "graphic-a",
        "filename: shared.png__E02",
        "graphic-b",
    )
    renames = [notice for notice in result.report.notices if notice.code == "attachment_renamed"]
    assert [(notice.source_label, notice.message) for notice in renames] == [
        ("E03", "attachment 'shared.ttf' renamed to 'shared.ttf__E03'"),
        ("E02", "attachment 'shared.png' renamed to 'shared.png__E02'"),
    ]
