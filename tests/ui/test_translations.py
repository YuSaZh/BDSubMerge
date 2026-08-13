from bdsubmerge.ui.translations import TranslationCatalog


def test_default_locale_is_simplified_chinese_and_can_switch_to_english() -> None:
    catalog = TranslationCatalog()
    assert catalog.locale == "zh_CN"
    assert catalog.text("path.label") == "原盘路径"

    catalog.set_locale("en_US")

    assert catalog.text("path.label") == "Blu-ray path"
    assert catalog.text("playlist.primary") == "Primary playlist"
    assert catalog.text("preflight.expected_styles", count=2) == "Expected styles: 2"
    assert catalog.text("confirm.warnings.message", count=2) == (
        "Preflight has 2 warnings. Generate subtitles anyway?"
    )
    assert catalog.text("subtitles.details") == "Source details"
    assert catalog.text("status.scan_complete", count=3) == "Scan complete: 3 playlists"
    assert catalog.text("timeline.zoom", percent=120) == "Zoom 120%"


def test_chinese_catalog_contains_localized_diagnostic_severity_and_message() -> None:
    catalog = TranslationCatalog()

    assert catalog.text("severity.warning") == "警告"
    assert catalog.text("issue.low_mapping_confidence") == (
        "低置信度自动映射需要明确确认"
    )


def test_unknown_translation_key_remains_visible() -> None:
    assert TranslationCatalog().text("missing.key") == "missing.key"
