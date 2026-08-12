from bdsubmerge.merge.report import MergeNotice, MergeReport, StyleRenameRecord


def test_merge_report_is_machine_serializable_without_subtitle_text() -> None:
    report = MergeReport(
        ("E01", "E02"),
        4,
        3,
        dropped_event_count=1,
        style_renames=(StyleRenameRecord("E02", "Default", "Default__E02"),),
        notices=(MergeNotice("warning", "event_dropped", "event was outside timeline", "E01"),),
    )

    payload = report.to_json()

    assert '"output_event_count": 3' in payload
    assert '"new_name": "Default__E02"' in payload
    assert "subtitle text" not in payload
