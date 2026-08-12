import pytest

from bdsubmerge.domain.timebase import MediaTick90k
from bdsubmerge.subtitles.pgs_adapter import (
    MAX_TIMESTAMP,
    PgsParseError,
    PgsSegmentType,
    PgsSource,
    PgsTimestampOverflowError,
    TimestampOverflowPolicy,
    append_sup_sources,
    estimate_sup_duration,
    parse_sup,
    shift_sup,
)


def _packet(pts: int, dts: int, segment_type: int, payload: bytes = b"") -> bytes:
    return b"".join(
        (
            b"PG",
            pts.to_bytes(4, "big"),
            dts.to_bytes(4, "big"),
            bytes((segment_type,)),
            len(payload).to_bytes(2, "big"),
            payload,
        )
    )


def _display_set(pts: int, payload: bytes = b"pcs") -> bytes:
    return _packet(pts, pts - 10, PgsSegmentType.PRESENTATION_COMPOSITION, payload) + _packet(
        pts,
        pts,
        PgsSegmentType.END,
    )


def test_parse_single_display_set_round_trips_payload_exactly() -> None:
    data = _display_set(1_000, b"\x00\x01opaque-pcs")
    document = parse_sup(data)
    assert len(document.packets) == 2
    assert document.packets[0].payload == b"\x00\x01opaque-pcs"
    assert document.warnings == ()
    assert document.to_bytes() == data


def test_multiple_display_sets_and_pts_dts_shift() -> None:
    document = parse_sup(_display_set(1_000) + _display_set(2_000))
    shifted = shift_sup(document, MediaTick90k(90_000))
    assert [packet.pts_90k for packet in shifted.packets] == [91_000, 91_000, 92_000, 92_000]
    assert [packet.dts_90k for packet in shifted.packets] == [90_990, 91_000, 91_990, 92_000]
    assert [packet.payload for packet in shifted.packets] == [
        packet.payload for packet in document.packets
    ]


def test_invalid_magic_is_rejected() -> None:
    with pytest.raises(PgsParseError, match="invalid PG magic"):
        parse_sup(b"XX" + _packet(0, 0, PgsSegmentType.END)[2:])


def test_truncated_header_and_payload_length_are_rejected() -> None:
    with pytest.raises(PgsParseError, match="truncated PGS packet header"):
        parse_sup(b"PG\x00")
    malformed = _packet(0, 0, PgsSegmentType.END)[:-2] + b"\x00\x02"
    with pytest.raises(PgsParseError, match="payload length 2 exceeds"):
        parse_sup(malformed)


def test_timestamp_overflow_errors_by_default_and_can_wrap() -> None:
    document = parse_sup(_packet(MAX_TIMESTAMP, MAX_TIMESTAMP, PgsSegmentType.END))
    with pytest.raises(PgsTimestampOverflowError, match="outside unsigned 32-bit"):
        shift_sup(document, MediaTick90k(1))
    wrapped = shift_sup(
        document,
        MediaTick90k(1),
        overflow_policy=TimestampOverflowPolicy.WRAP,
    )
    assert wrapped.packets[0].pts_90k == 0
    assert wrapped.packets[0].dts_90k == 0


def test_negative_timestamp_shift_uses_same_overflow_policy() -> None:
    document = parse_sup(_packet(0, 0, PgsSegmentType.END))
    with pytest.raises(PgsTimestampOverflowError):
        shift_sup(document, MediaTick90k(-1))
    wrapped = shift_sup(
        document,
        MediaTick90k(-1),
        overflow_policy=TimestampOverflowPolicy.WRAP,
    )
    assert wrapped.packets[0].pts_90k == MAX_TIMESTAMP


def test_append_preserves_caller_source_order() -> None:
    first = parse_sup(_display_set(100, b"first"))
    second = parse_sup(_display_set(200, b"second"))
    merged = append_sup_sources(
        (
            PgsSource(first, MediaTick90k(1_000), "episode 1"),
            PgsSource(second, MediaTick90k(2_000), "episode 2"),
        )
    )
    assert [packet.payload for packet in merged.packets if packet.payload] == [
        b"first",
        b"second",
    ]
    assert [packet.pts_90k for packet in merged.packets] == [1_100, 1_100, 2_200, 2_200]


def test_non_monotonic_timestamps_are_reported() -> None:
    document = parse_sup(_display_set(2_000) + _display_set(1_000))
    assert any("non-monotonic PTS" in warning for warning in document.warnings)
    assert any("non-monotonic DTS" in warning for warning in document.warnings)


def test_missing_end_and_unknown_segment_are_reported_without_data_loss() -> None:
    data = _packet(100, 90, PgsSegmentType.PRESENTATION_COMPOSITION, b"pcs") + _packet(
        100,
        90,
        0x99,
        b"unknown",
    )
    document = parse_sup(data)
    assert any("missing an END" in warning for warning in document.warnings)
    assert any("unsupported segment type 0x99" in warning for warning in document.warnings)
    assert document.to_bytes() == data


def test_duration_prefers_explicit_clear_screen_presentation_timestamp() -> None:
    visible_pcs = b"\x07\x80\x04\x38\x10\x00\x01\x00\x00\x00\x01"
    clear_pcs = b"\x07\x80\x04\x38\x10\x00\x02\x00\x00\x00\x00"
    document = parse_sup(
        _packet(1_000, 990, PgsSegmentType.PRESENTATION_COMPOSITION, visible_pcs)
        + _packet(1_000, 1_000, PgsSegmentType.END)
        + _packet(2_000, 1_990, PgsSegmentType.PRESENTATION_COMPOSITION, clear_pcs)
        + _packet(2_000, 2_000, PgsSegmentType.END)
        + _packet(3_000, 3_000, PgsSegmentType.PALETTE_DEFINITION, b"palette")
    )

    duration = estimate_sup_duration(document)

    assert duration.earliest_pts_90k == 1_000
    assert duration.raw_end_90k == 3_000
    assert duration.effective_end_90k == 2_000
    assert duration.estimated is False


def test_duration_without_clear_screen_is_marked_estimated() -> None:
    document = parse_sup(_display_set(1_000))

    duration = estimate_sup_duration(document)

    assert duration.effective_end_90k == 1_000
    assert duration.estimated is True
