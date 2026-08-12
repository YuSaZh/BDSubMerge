from bdsubmerge.mapping import (
    BoundaryKind,
    BoundarySource,
    MediaTick90k,
    boundary,
    merge_boundaries,
)


def test_merge_boundaries_is_ordered_and_retains_all_sources() -> None:
    chapter = boundary(
        "chapter-1",
        90_000,
        BoundarySource(BoundaryKind.CHAPTER, "mark:1"),
        confidence=80,
    )
    play_item = boundary(
        "item-1",
        90_045,
        BoundarySource(BoundaryKind.PLAY_ITEM_START, "item:1"),
        confidence=95,
        note="clip boundary",
    )

    merged = merge_boundaries((play_item, chapter), tolerance_90k=MediaTick90k(45))

    assert len(merged) == 1
    assert merged[0].id == "chapter-1"
    assert merged[0].time_90k == 90_000
    assert merged[0].kinds == {
        BoundaryKind.CHAPTER,
        BoundaryKind.PLAY_ITEM_START,
    }
    assert merged[0].confidence == 95
    assert merged[0].note == "clip boundary"


def test_disabled_boundary_group_becomes_enabled_when_any_source_is_enabled() -> None:
    source = BoundarySource(BoundaryKind.CHAPTER)
    disabled = boundary("a", 0, source, enabled=False)
    enabled = boundary("b", 0, source)

    assert merge_boundaries((disabled, enabled))[0].enabled is True
