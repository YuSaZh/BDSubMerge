"""Deterministic ASS style and override-reference merging."""

from __future__ import annotations

from dataclasses import dataclass

from .ass_document import AssEvent, AssStyle


@dataclass(frozen=True, slots=True)
class StyleRename:
    source_label: str
    old_name: str
    new_name: str


@dataclass(frozen=True, slots=True)
class StyleMergeResult:
    styles: tuple[AssStyle, ...]
    events: tuple[AssEvent, ...]
    renames: tuple[StyleRename, ...]
    name_map: dict[str, str]


def _sanitize_label(label: str) -> str:
    sanitized = "".join(character if character.isalnum() else "_" for character in label).strip("_")
    return sanitized or "Source"


def _unique_style_name(base: str, source_label: str, occupied: set[str]) -> str:
    stem = f"{base}__{_sanitize_label(source_label)}"
    candidate = stem
    suffix = 2
    occupied_folded = {name.casefold() for name in occupied}
    while candidate.casefold() in occupied_folded:
        candidate = f"{stem}_{suffix}"
        suffix += 1
    return candidate


def rewrite_override_style_references(text: str, name_map: dict[str, str]) -> str:
    r"""Rewrite complete ``\rStyle`` arguments inside override blocks only."""

    folded_map = {key.casefold(): value for key, value in name_map.items()}
    result: list[str] = []
    position = 0
    while position < len(text):
        opening = text.find("{", position)
        if opening < 0:
            result.append(text[position:])
            break
        closing = text.find("}", opening + 1)
        if closing < 0:
            result.append(text[position:])
            break
        result.append(text[position : opening + 1])
        block = text[opening + 1 : closing]
        result.append(_rewrite_override_block(block, folded_map))
        result.append("}")
        position = closing + 1
    return "".join(result)


def _rewrite_override_block(block: str, name_map: dict[str, str]) -> str:
    pieces: list[str] = []
    position = 0
    while position < len(block):
        tag_start = block.find("\\", position)
        if tag_start < 0:
            pieces.append(block[position:])
            break
        pieces.append(block[position:tag_start])
        next_tag = block.find("\\", tag_start + 1)
        tag_end = len(block) if next_tag < 0 else next_tag
        tag = block[tag_start:tag_end]
        if len(tag) >= 2 and tag[1].casefold() == "r":
            argument = tag[2:]
            replacement = name_map.get(argument.casefold())
            if argument and replacement is not None:
                tag = f"{tag[:2]}{replacement}"
        pieces.append(tag)
        position = tag_end
    return "".join(pieces)


def rewrite_event_styles(event: AssEvent, name_map: dict[str, str]) -> AssEvent:
    folded_map = {key.casefold(): value for key, value in name_map.items()}
    style = event.value("Style")
    if style is not None and style.casefold() in folded_map:
        event = event.with_value("Style", folded_map[style.casefold()])
    text = event.value("Text")
    if text is not None:
        event = event.with_value("Text", rewrite_override_style_references(text, name_map))
    return event


def merge_style_set(
    existing_styles: tuple[AssStyle, ...],
    incoming_styles: tuple[AssStyle, ...],
    incoming_events: tuple[AssEvent, ...],
    *,
    source_label: str,
) -> StyleMergeResult:
    """Merge one source's styles and update that source's style references."""

    merged = list(existing_styles)
    occupied = {style.name for style in merged}
    by_name: dict[str, list[AssStyle]] = {}
    for style in merged:
        by_name.setdefault(style.name.casefold(), []).append(style)
    name_map: dict[str, str] = {}
    renames: list[StyleRename] = []
    for style in incoming_styles:
        matches = by_name.get(style.name.casefold(), [])
        if any(candidate.definition() == style.definition() for candidate in matches):
            continue
        if matches:
            new_name = _unique_style_name(style.name, source_label, occupied)
            name_map[style.name] = new_name
            renames.append(StyleRename(source_label, style.name, new_name))
            style = style.with_value("Name", new_name)
        merged.append(style)
        occupied.add(style.name)
        by_name.setdefault(style.name.casefold(), []).append(style)
    events = tuple(rewrite_event_styles(event, name_map) for event in incoming_events)
    return StyleMergeResult(tuple(merged), events, tuple(renames), name_map)
