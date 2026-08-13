from bdsubmerge.ui.translations import TranslationCatalog


def test_default_locale_is_simplified_chinese_and_can_switch_to_english() -> None:
    catalog = TranslationCatalog()
    assert catalog.locale == "zh_CN"
    assert catalog.text("path.label") == "原盘路径"

    catalog.set_locale("en_US")

    assert catalog.text("path.label") == "Blu-ray path"
    assert catalog.text("playlist.primary") == "Primary playlist"
    assert catalog.text("preflight.expected_styles", count=2) == "Expected styles: 2"
    assert catalog.text("subtitles.details") == "Source details"
    assert catalog.text("status.scan_complete", count=3) == "Scan complete: 3 playlists"


def test_unknown_translation_key_remains_visible() -> None:
    assert TranslationCatalog().text("missing.key") == "missing.key"
