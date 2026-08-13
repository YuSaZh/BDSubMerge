from bdsubmerge.cancellation import progress_scope
from bdsubmerge.merge.engine import merge_srt
from bdsubmerge.merge.plan import MergePlan, MergeSource
from bdsubmerge.subtitles.srt_document import parse_srt


def test_srt_merge_shifts_renumbers_and_warns_on_overlap() -> None:
    first = parse_srt("1\n00:00:00,000 --> 00:00:02,000\none\n")
    second = parse_srt("1\n00:00:00,000 --> 00:00:02,000\ntwo\n")

    result = merge_srt(
        MergePlan((MergeSource("E01", first, 0), MergeSource("E02", second, 90_000)))
    )

    assert [cue.start_ticks for cue in result.document.cues] == [0, 90_000]
    assert "\ufeff1\n00:00:00,000 --> 00:00:02,000" in result.document.serialize()
    assert any(notice.code == "cue_overlap" for notice in result.report.notices)


def test_srt_merge_reports_current_source_detail() -> None:
    source_path = "/media/Subtitles/E01.srt"
    document = parse_srt("1\n00:00:00,000 --> 00:00:02,000\none\n")
    progress: list[tuple[int, str]] = []

    with progress_scope(lambda value, detail: progress.append((value, detail))):
        merge_srt(MergePlan((MergeSource("E01", document, 0, source_path),)))

    assert any(detail == source_path for _, detail in progress)
