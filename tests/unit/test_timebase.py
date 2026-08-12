from bdsubmerge.domain.timebase import (
    MediaTick90k,
    RoundingMode,
    from_45k,
    serialized_interval,
    to_centiseconds,
    to_milliseconds,
)


def test_45khz_conversion_is_exact() -> None:
    assert from_45k(45_000) == 90_000


def test_text_rounding_is_explicit_and_outward() -> None:
    value = MediaTick90k(1_001)
    assert to_milliseconds(value, RoundingMode.FLOOR) == 11
    assert to_milliseconds(value, RoundingMode.CEIL) == 12
    assert to_centiseconds(value, RoundingMode.FLOOR) == 1
    assert to_centiseconds(value, RoundingMode.CEIL) == 2


def test_serialized_interval_remains_positive() -> None:
    assert serialized_interval(MediaTick90k(899), MediaTick90k(899), quantum=900) == (0, 1)


def test_negative_values_round_mathematically() -> None:
    assert to_milliseconds(MediaTick90k(-91), RoundingMode.FLOOR) == -2
    assert to_milliseconds(MediaTick90k(-91), RoundingMode.CEIL) == -1
