from bdsubmerge.subtitles.ass_document import parse_ass
from bdsubmerge.subtitles.text_adapter import analyze_text_subtitle


def test_analysis_ignores_comment_and_long_tail_for_effective_end() -> None:
    document = parse_ass(
        "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
        "[V4+ Styles]\nFormat: Name\nStyle: Default\n"
        "[Events]\nFormat: Start, End, Style, Text\n"
        "Dialogue: 0:00:00.00,0:01:00.00,Default,normal\n"
        "Dialogue: 0:01:00.00,0:01:30.00,Default,normal\n"
        "Dialogue: 0:01:30.00,0:10:00.00,Default,long tail\n"
        "Comment: 0:00:00.00,0:20:00.00,Default,note\n"
    )

    info = analyze_text_subtitle(document)

    assert info.raw_end_ticks == 108_000_000
    assert info.effective_end_ticks == 8_100_000
    assert info.suspected_long_tail is True
    assert (info.play_res_x, info.play_res_y) == (1920, 1080)
