from bdsubmerge.subtitles.ass_document import AssDocument, parse_ass
from bdsubmerge.subtitles.style_merger import (
    merge_style_set,
    rewrite_override_style_references,
)


def _document(color: str, text: str) -> AssDocument:
    return parse_ass(
        "[Script Info]\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour\n"
        f"Style: Default,Arial,48,{color}\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:01.00,Default,{text}\n"
    )


def test_style_conflict_renames_definition_event_and_override_reference() -> None:
    first = _document("&H00FFFFFF", "one")
    second = _document("&H0000FFFF", r"{\bord2\rDefault\c&HFF0000&}two")

    result = merge_style_set(first.styles, second.styles, second.events, source_label="E02")

    assert [style.name for style in result.styles] == ["Default", "Default__E02"]
    assert result.events[0].value("Style") == "Default__E02"
    assert result.events[0].value("Text") == r"{\bord2\rDefault__E02\c&HFF0000&}two"
    assert result.renames[0].new_name == "Default__E02"


def test_equal_style_definition_is_deduplicated() -> None:
    first = _document("&H00FFFFFF", "one")
    second = _document("&H00FFFFFF", "two")

    result = merge_style_set(first.styles, second.styles, second.events, source_label="E02")

    assert result.styles == first.styles
    assert result.renames == ()


def test_multiple_conflicts_get_stable_suffixes() -> None:
    first = _document("&H00FFFFFF", "one")
    second = _document("&H0000FFFF", "two")
    third = _document("&H00FF00FF", "three")
    step = merge_style_set(first.styles, second.styles, second.events, source_label="E02")

    result = merge_style_set(step.styles, third.styles, third.events, source_label="E02")

    assert result.styles[-1].name == "Default__E02_2"


def test_override_parser_ignores_plain_text_partial_names_and_bare_reset() -> None:
    text = r"Default outside {\r\bord1} {\rDefaultLong} {\rDefault}"

    result = rewrite_override_style_references(text, {"Default": "Default__E02"})

    assert result == r"Default outside {\r\bord1} {\rDefaultLong} {\rDefault__E02}"
