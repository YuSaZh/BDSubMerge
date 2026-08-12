"""Lossless timestamp transformation for Blu-ray PGS/SUP packet streams."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from enum import IntEnum, StrEnum

from bdsubmerge.domain.timebase import MediaTick90k

PG_MAGIC = b"PG"
PACKET_HEADER_SIZE = 13
MAX_TIMESTAMP = (1 << 32) - 1


class PgsParseError(ValueError):
    """Raised when a SUP byte stream is structurally invalid."""


class PgsTimestampOverflowError(OverflowError):
    """Raised when shifting would leave the unsigned 32-bit PGS time range."""


class PgsSegmentType(IntEnum):
    PALETTE_DEFINITION = 0x14
    OBJECT_DEFINITION = 0x15
    PRESENTATION_COMPOSITION = 0x16
    WINDOW_DEFINITION = 0x17
    END = 0x80


class TimestampOverflowPolicy(StrEnum):
    ERROR = "error"
    WRAP = "wrap"


@dataclass(frozen=True, slots=True)
class PgsPacket:
    pts_90k: MediaTick90k
    dts_90k: MediaTick90k
    segment_type: int
    payload: bytes

    def to_bytes(self) -> bytes:
        """Serialize exactly, preserving the segment type and payload bytes."""
        if len(self.payload) > 0xFFFF:
            raise PgsParseError("PGS segment payload exceeds the 16-bit length field")
        return b"".join(
            (
                PG_MAGIC,
                int(self.pts_90k).to_bytes(4, "big"),
                int(self.dts_90k).to_bytes(4, "big"),
                bytes((self.segment_type,)),
                len(self.payload).to_bytes(2, "big"),
                self.payload,
            )
        )


@dataclass(frozen=True, slots=True)
class PgsDocument:
    packets: tuple[PgsPacket, ...]
    warnings: tuple[str, ...] = ()

    def to_bytes(self) -> bytes:
        return b"".join(packet.to_bytes() for packet in self.packets)


@dataclass(frozen=True, slots=True)
class PgsDurationInfo:
    """Best available duration projection for automatic episode mapping."""

    earliest_pts_90k: MediaTick90k | None
    raw_end_90k: MediaTick90k | None
    effective_end_90k: MediaTick90k | None
    estimated: bool


@dataclass(frozen=True, slots=True)
class PgsSource:
    document: PgsDocument
    offset_90k: MediaTick90k = field(default_factory=lambda: MediaTick90k(0))
    label: str = ""


def _validate_timestamp(value: int, *, field: str, packet_index: int) -> MediaTick90k:
    if not 0 <= value <= MAX_TIMESTAMP:
        raise PgsParseError(f"packet {packet_index} {field} is outside unsigned 32-bit range")
    return MediaTick90k(value)


def _timeline_warnings(packets: Iterable[PgsPacket]) -> tuple[str, ...]:
    warnings: list[str] = []
    previous_pts: MediaTick90k | None = None
    previous_nonzero_dts: MediaTick90k | None = None
    open_display_set: int | None = None
    known_types = {member.value for member in PgsSegmentType}

    for index, packet in enumerate(packets):
        if previous_pts is not None and packet.pts_90k < previous_pts:
            warnings.append(f"packet {index} has a non-monotonic PTS")
        previous_pts = packet.pts_90k
        if packet.dts_90k:
            if previous_nonzero_dts is not None and packet.dts_90k < previous_nonzero_dts:
                warnings.append(f"packet {index} has a non-monotonic DTS")
            previous_nonzero_dts = packet.dts_90k

        if packet.segment_type not in known_types:
            warnings.append(
                f"packet {index} uses unsupported segment type 0x{packet.segment_type:02X}"
            )
        if packet.segment_type == PgsSegmentType.PRESENTATION_COMPOSITION:
            if open_display_set is not None:
                warnings.append(
                    f"display set at packet {open_display_set} is missing an END segment"
                )
            open_display_set = index
        elif packet.segment_type == PgsSegmentType.END:
            if open_display_set is None:
                warnings.append(f"packet {index} has an END segment without an open display set")
            open_display_set = None

    if open_display_set is not None:
        warnings.append(f"display set at packet {open_display_set} is missing an END segment")
    return tuple(warnings)


def parse_sup(data: bytes) -> PgsDocument:
    """Parse a complete SUP stream without decoding or rewriting segment payloads."""
    packets: list[PgsPacket] = []
    offset = 0
    while offset < len(data):
        remaining = len(data) - offset
        if remaining < PACKET_HEADER_SIZE:
            raise PgsParseError(
                f"truncated PGS packet header at byte {offset}: {remaining} bytes remain"
            )
        if data[offset : offset + 2] != PG_MAGIC:
            magic = data[offset : offset + 2].hex().upper()
            raise PgsParseError(f"invalid PG magic at byte {offset}: 0x{magic}")

        pts = int.from_bytes(data[offset + 2 : offset + 6], "big")
        dts = int.from_bytes(data[offset + 6 : offset + 10], "big")
        segment_type = data[offset + 10]
        payload_length = int.from_bytes(data[offset + 11 : offset + 13], "big")
        packet_end = offset + PACKET_HEADER_SIZE + payload_length
        if packet_end > len(data):
            available = len(data) - offset - PACKET_HEADER_SIZE
            raise PgsParseError(
                f"packet {len(packets)} payload length {payload_length} exceeds "
                f"the {available} available bytes"
            )
        packets.append(
            PgsPacket(
                pts_90k=_validate_timestamp(pts, field="PTS", packet_index=len(packets)),
                dts_90k=_validate_timestamp(dts, field="DTS", packet_index=len(packets)),
                segment_type=segment_type,
                payload=data[offset + PACKET_HEADER_SIZE : packet_end],
            )
        )
        offset = packet_end

    immutable_packets = tuple(packets)
    return PgsDocument(immutable_packets, _timeline_warnings(immutable_packets))


def estimate_sup_duration(document: PgsDocument) -> PgsDurationInfo:
    """Estimate the display duration, preferring an explicit clear-screen PCS.

    A Presentation Composition Segment declares its object count at byte 10. A
    zero-object PCS following visible content clears the screen and therefore gives
    a stronger end timestamp than the last packet in the stream.
    """

    if not document.packets:
        return PgsDurationInfo(None, None, None, True)
    timestamps = tuple(packet.pts_90k for packet in document.packets)
    visible_content_seen = False
    clear_pts: list[MediaTick90k] = []
    for packet in document.packets:
        if packet.segment_type != PgsSegmentType.PRESENTATION_COMPOSITION:
            continue
        if len(packet.payload) < 11:
            continue
        object_count = packet.payload[10]
        if object_count:
            visible_content_seen = True
        elif visible_content_seen:
            clear_pts.append(packet.pts_90k)
    raw_end = max(timestamps)
    effective_end = max(clear_pts) if clear_pts else raw_end
    return PgsDurationInfo(min(timestamps), raw_end, effective_end, not bool(clear_pts))


def _shift_timestamp(
    value: MediaTick90k,
    offset: MediaTick90k,
    *,
    policy: TimestampOverflowPolicy,
    field: str,
    packet_index: int,
) -> MediaTick90k:
    shifted = int(value) + int(offset)
    if 0 <= shifted <= MAX_TIMESTAMP:
        return MediaTick90k(shifted)
    if policy is TimestampOverflowPolicy.WRAP:
        return MediaTick90k(shifted & MAX_TIMESTAMP)
    raise PgsTimestampOverflowError(
        f"packet {packet_index} {field} shift produced {shifted}, outside unsigned 32-bit range"
    )


def shift_sup(
    document: PgsDocument,
    offset_90k: MediaTick90k,
    *,
    overflow_policy: TimestampOverflowPolicy = TimestampOverflowPolicy.ERROR,
) -> PgsDocument:
    """Shift PTS and DTS while leaving every segment payload unchanged."""
    shifted = tuple(
        replace(
            packet,
            pts_90k=_shift_timestamp(
                packet.pts_90k,
                offset_90k,
                policy=overflow_policy,
                field="PTS",
                packet_index=index,
            ),
            dts_90k=_shift_timestamp(
                packet.dts_90k,
                offset_90k,
                policy=overflow_policy,
                field="DTS",
                packet_index=index,
            ),
        )
        for index, packet in enumerate(document.packets)
    )
    warnings = document.warnings + _timeline_warnings(shifted)
    return PgsDocument(shifted, tuple(dict.fromkeys(warnings)))


def append_sup_sources(
    sources: Sequence[PgsSource],
    *,
    overflow_policy: TimestampOverflowPolicy = TimestampOverflowPolicy.ERROR,
) -> PgsDocument:
    """Shift and append sources in caller-provided order without re-encoding."""
    packets: list[PgsPacket] = []
    warnings: list[str] = []
    for source_index, source in enumerate(sources):
        shifted = shift_sup(
            source.document,
            source.offset_90k,
            overflow_policy=overflow_policy,
        )
        packets.extend(shifted.packets)
        prefix = source.label or f"source {source_index}"
        warnings.extend(f"{prefix}: {warning}" for warning in shifted.warnings)
    warnings.extend(_timeline_warnings(packets))
    return PgsDocument(tuple(packets), tuple(dict.fromkeys(warnings)))
