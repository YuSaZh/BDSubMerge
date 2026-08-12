from bdsubmerge.subtitles.ass_document import (
    AssEvent,
    AssRawLine,
    format_ass_time,
    parse_ass,
    parse_ass_time,
)


ASS_TEXT = """\ufeff[Script Info]\r
PlayResY: 1080\r
PlayResX: 1920\r
\r
[V4+ Styles]\r
Format: Fontname, Name, Fontsize, PrimaryColour\r
Style: Arial,Default,48,&H00FFFFFF\r
\r
[Events]\r
Format: Text, End, Start, Style, Layer\r
Dialogue: Hello, world,0:00:02.34,0:00:01.23,Default,7\r
Comment: {note},0:00:03.00,0:00:02.50,Default,0\r
\r
[Vendor Private]\r
Opaque: a,b,c\r
"""


def test_parse_uses_declared_format_and_preserves_unknown_section() -> None:
    document = parse_ass(ASS_TEXT)

    assert document.bom is True
    assert document.newline == "\r\n"
    assert document.styles[0].name == "Default"
    assert document.styles[0].value("Fontname") == "Arial"
    assert document.events[0].value("Text") == "Hello, world"
    assert document.events[0].value("Layer") == "7"
    private = document.section("vendor private")
    assert private is not None
    assert private.entries == (AssRawLine("Opaque: a,b,c"),)


def test_ass_round_trip_retains_bom_comments_and_custom_content() -> None:
    result = parse_ass(ASS_TEXT).serialize()

    assert result.startswith("\ufeff[Script Info]")
    assert "Comment: {note},0:00:03.00,0:00:02.50,Default,0" in result
    assert "[Vendor Private]\r\nOpaque: a,b,c" in result


def test_ass_time_rounds_outward_and_keeps_nonempty_event() -> None:
    assert parse_ass_time("1:02:03.45") == 335_110_500
    assert format_ass_time(899) == "0:00:00.00"
    assert format_ass_time(899, is_end=True, start_ticks=0) == "0:00:00.01"
    assert format_ass_time(900, is_end=True, start_ticks=900) == "0:00:00.02"


def test_events_are_project_owned_integer_tick_records() -> None:
    event = parse_ass(ASS_TEXT).events[0]

    assert isinstance(event, AssEvent)
    assert event.start_ticks == 110_700
    assert event.end_ticks == 210_600
