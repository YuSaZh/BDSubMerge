from pathlib import Path

import pytest

from bdsubmerge.merge.engine import merge_ass
from bdsubmerge.merge.plan import MergePlan, MergeSource
from bdsubmerge.subtitles.ass_document import parse_ass


@pytest.mark.golden
def test_complex_ass_merge_matches_golden_file() -> None:
    first = parse_ass(
        "\ufeff[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
        "[V4+ Styles]\nFormat: Name,Fontname,PrimaryColour\n"
        "Style: Default,Arial,white\n"
        "[Events]\nFormat: Text,Style,End,Start,Layer\n"
        r"Dialogue: {\rDefault}one,Default,0:00:01.00,0:00:00.00,0" "\n"
        "[Private Data]\nopaque=a,b\n"
    )
    second = parse_ass(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
        "[V4+ Styles]\nFormat: PrimaryColour,Fontname,Name\n"
        "Style: yellow,Arial,Default\n"
        "[Events]\nFormat: Layer,Start,End,Style,Text\n"
        r"Dialogue: 1,0:00:00.00,0:00:01.00,Default,{\rDefault}two" "\n"
        "[Private Data]\nopaque=c,d\n"
    )

    merged = merge_ass(
        MergePlan((MergeSource("E01", first, 0), MergeSource("E02", second, 180_000)))
    )
    golden = Path("tests/golden/complex_ass_expected.ass").read_text(encoding="utf-8-sig")

    assert merged.document.serialize().removeprefix("\ufeff") == golden
