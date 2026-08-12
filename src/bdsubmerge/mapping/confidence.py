"""Confidence classification for automatic timeline mappings."""

from __future__ import annotations

from .models import MappingConfidence, MappingCostConfig


def classify_confidence(
    *,
    cost: int,
    reference_duration_90k: int,
    alternative_cost: int | None,
    config: MappingCostConfig,
) -> MappingConfidence:
    if reference_duration_90k <= 0:
        return MappingConfidence.LOW
    cost_ratio = cost * 100 // reference_duration_90k
    ambiguous = (
        alternative_cost is not None
        and (alternative_cost - cost) * 100
        <= reference_duration_90k * config.ambiguity_margin_percent
    )
    if cost_ratio >= config.low_cost_ratio_percent or ambiguous:
        return MappingConfidence.LOW
    if cost_ratio >= config.medium_cost_ratio_percent:
        return MappingConfidence.MEDIUM
    return MappingConfidence.HIGH


def lowest_confidence(values: tuple[MappingConfidence, ...]) -> MappingConfidence:
    rank = {
        MappingConfidence.HIGH: 0,
        MappingConfidence.MEDIUM: 1,
        MappingConfidence.LOW: 2,
    }
    return max(values, key=rank.__getitem__, default=MappingConfidence.LOW)
