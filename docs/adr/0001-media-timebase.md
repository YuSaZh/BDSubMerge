# ADR 0001: Integer 90 kHz media timebase

- Status: accepted
- Date: 2026-08-13

## Decision

All core timeline values use a distinct integer `MediaTick90k` type representing 90,000
ticks per second. Floating-point seconds are prohibited in timeline calculations.

MPLS 45 kHz values convert exactly by multiplication by two. ASS/SSA centiseconds are
900 ticks, SRT milliseconds are 90 ticks, and PGS timestamps already use 90 kHz.

Text serialization rounds starts downward and ends upward to the target format precision,
then guarantees that every serialized end remains greater than its start.

## Consequences

- Repeated playlist accumulation cannot introduce floating-point drift.
- Conversions must state their rounding policy explicitly.
- UI display values are projections and never become the source of truth.
