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
