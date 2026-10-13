from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from calco.maplibre.expressions import (
    Untranslatable,
    else_expression,
    filter_expression,
    text_field,
)
from calco.maplibre.label_rules import LabelRule, read_label_rules
from calco.maplibre.zoom import zoom_range
from calco.model import StyledLayer, StyledLayerDescriptor
from calco.symbolizers import Fill, Font, LinePlacement, PointPlacement
from calco.values import parse_number

FontStack = Callable[[Font], list[str]]
IGNORED_OPTIONS = frozenset(
    {"group", "labelAllGroup", "partials", "goodnessOfFit", "maxDisplacement", "polygonAlign"}
)


@dataclass(frozen=True)
class Skipped:
    layer: str
    index: int
    reason: str


@dataclass(frozen=True)
class LabelLayers:
    layers: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def default_fonts(font: Font) -> list[str]:
    bold = font.weight == "bold"
    italic = font.style in ("italic", "oblique")
    suffix = " ".join(word for word, on in (("Bold", bold), ("Italic", italic)) if on)
    return [f"{font.family} {suffix or 'Regular'}"]


def color(fill: Fill) -> str:
    if fill.opacity == 1:
        return fill.color
    red, green, blue = (int(fill.color[index : index + 2], 16) for index in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {fill.opacity})"


def label_layers(
    sld: StyledLayerDescriptor | StyledLayer,
    *,
    source: str,
    source_layer: str | None = None,
    fonts: FontStack | None = None,
    id_prefix: str = "calco",
    tile_size: int = 512,
    style: str | None = None,
) -> LabelLayers:
    result = LabelLayers()
    layers = sld.layers if isinstance(sld, StyledLayerDescriptor) else (sld,)
    for candidate in layers:
        if candidate.user_styles and candidate.pick_style(style) is None:
            reason = (
                f"no user style named {style}" if style else "several user styles, none default"
            )
            result.skipped.append(Skipped(candidate.name, -1, reason))
    for label in read_label_rules(sld, style):
        try:
            layer = _layer(label, source, fonts or default_fonts, id_prefix, tile_size, result)
        except Untranslatable as exc:
            result.skipped.append(Skipped(label.layer, label.index, str(exc)))
            continue
        if source_layer is not None:
            layer["source-layer"] = source_layer
        result.layers.append(layer)
    return result


def _layer(
    label: LabelRule,
    source: str,
    fonts: FontStack,
    id_prefix: str,
    tile_size: int,
    result: LabelLayers,
) -> dict[str, Any]:
    text = label.text
    font = text.font or Font()
    where = f"{label.layer}#{label.index}"
    layout: dict[str, Any] = {
        "text-field": text_field(text.parts),
        "text-font": fonts(font),
        "text-size": font.size,
    }
    paint: dict[str, Any] = {"text-color": color(text.fill or Fill("#000000"))}
    if text.halo is not None:
        paint["text-halo-color"] = color(text.halo.fill)
        paint["text-halo-width"] = text.halo.radius
    _placement(layout, text.placement or PointPlacement(0, 0.5), font.size)
    _vendor_options(layout, text.vendor_options, font.size, where, result)
    if text.geometry is not None:
        result.notes.append(f"{where}: label geometry ignored, MapLibre picks the anchor point")
    layer: dict[str, Any] = {
        "id": f"{id_prefix}-{re.sub(r'[^0-9A-Za-z_-]+', '_', label.layer)}-{label.index}",
        "type": "symbol",
        "source": source,
        **zoom_range(label.rule.scales.min, label.rule.scales.max, tile_size),
        "layout": layout,
        "paint": paint,
    }
    if label.rule.filter is not None:
        layer["filter"] = filter_expression(label.rule.filter)
    elif label.rule.else_filter:
        expression = else_expression(label.siblings)
        if expression is not None:
            layer["filter"] = expression
    return layer


def _anchor(value: float, low: str, high: str) -> str:
    if value < 0.25:
        return low
    return high if value > 0.75 else ""


def _placement(
    layout: dict[str, Any], placement: PointPlacement | LinePlacement, size: float
) -> None:
    em = size or 1
    if isinstance(placement, LinePlacement):
        layout["symbol-placement"] = "line"
        if placement.offset:
            layout["text-offset"] = [0, -placement.offset / em]
        return
    vertical = _anchor(placement.anchor_y, "bottom", "top")
    horizontal = _anchor(placement.anchor_x, "left", "right")
    layout["text-anchor"] = "-".join(part for part in (vertical, horizontal) if part) or "center"
    if placement.displacement_x or placement.displacement_y:
        layout["text-offset"] = [placement.displacement_x / em, -placement.displacement_y / em]
    if placement.rotation:
        layout["text-rotate"] = placement.rotation


def _vendor_options(
    layout: dict[str, Any], options: dict[str, str], size: float, where: str, result: LabelLayers
) -> None:
    for name, raw in options.items():
        value = parse_number(raw)
        if name == "followLine":
            if raw.lower() == "true":
                layout["symbol-placement"] = "line"
        elif name == "conflictResolution":
            if raw.lower() == "false":
                layout["text-allow-overlap"] = True
                layout["text-ignore-placement"] = True
        elif name in ("autoWrap", "spaceAround", "repeat", "maxAngleDelta") and value is None:
            result.notes.append(f"{where}: vendor option {name}={raw!r} is not a number")
        elif name == "autoWrap" and value is not None:
            layout["text-max-width"] = value / (size or 1)
        elif name == "spaceAround" and value is not None:
            if value < 0:
                layout["text-allow-overlap"] = True
            else:
                layout["text-padding"] = value
        elif name == "repeat" and value is not None:
            layout["symbol-spacing"] = value
        elif name == "maxAngleDelta" and value is not None:
            layout["text-max-angle"] = value
        else:
            kind = "has no MapLibre equivalent" if name in IGNORED_OPTIONS else "is unknown"
            result.notes.append(f"{where}: vendor option {name} {kind}, ignored")
