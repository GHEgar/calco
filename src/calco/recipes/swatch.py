from __future__ import annotations

from typing import Any, Literal, Protocol

from calco.errors import InvalidModel, NotRecognized
from calco.expressions import Expression
from calco.model import Rule
from calco.symbolizers import (
    Fill,
    Graphic,
    LineSymbolizer,
    Mark,
    PointSymbolizer,
    PolygonSymbolizer,
    Stroke,
    Symbolizer,
)
from calco.values import choice, in_range, non_negative, required_text, set_field

Kind = Literal["polygon", "line", "point"]
KINDS: tuple[str, ...] = ("polygon", "line", "point")
DEFAULT_SIZE = 8
DEFAULT_MARK = "circle"


class Swatched(Protocol):
    @property
    def kind(self) -> str: ...
    @property
    def stroke(self) -> Stroke | None: ...
    @property
    def fill_opacity(self) -> float: ...
    @property
    def size(self) -> float: ...
    @property
    def mark(self) -> str: ...
    @property
    def geometry(self) -> Expression | None: ...


def check_swatch(target: Swatched, owner: str) -> None:
    kind = choice(target.kind, f"{owner}.kind", KINDS)
    set_field(target, "fill_opacity", in_range(target.fill_opacity, "fill_opacity", 0, 1))
    if target.stroke is not None and not isinstance(target.stroke, Stroke):
        raise InvalidModel(f"{owner}.stroke must be a Stroke")
    size = non_negative(target.size, f"{owner}.size")
    set_field(target, "size", size if kind != "polygon" else DEFAULT_SIZE)
    mark = required_text(target.mark, f"{owner}.mark")
    set_field(target, "mark", mark if kind == "point" else DEFAULT_MARK)
    if kind == "line":
        set_field(target, "stroke", None)


def class_symbolizer(target: Swatched, color: str) -> Symbolizer:
    fill = Fill(color, target.fill_opacity)
    if target.kind == "line":
        return LineSymbolizer(Stroke(color, target.size, target.fill_opacity), target.geometry)
    if target.kind == "point":
        graphic = Graphic(Mark(target.mark, fill, target.stroke), size=target.size)
        return PointSymbolizer(graphic, target.geometry)
    return PolygonSymbolizer(fill, target.stroke, target.geometry)


def read_class_symbolizer(rule: Rule, what: str) -> tuple[str, dict[str, Any]]:
    if len(rule.symbolizers) != 1:
        raise NotRecognized(f"{what} must hold exactly one symbolizer")
    symbolizer = rule.symbolizers[0]
    shared: dict[str, Any] = {
        "geometry": getattr(symbolizer, "geometry", None),
        "scales": rule.scales,
        "size": DEFAULT_SIZE,
        "mark": DEFAULT_MARK,
    }
    if isinstance(symbolizer, PolygonSymbolizer) and isinstance(symbolizer.fill, Fill):
        fill = symbolizer.fill
        shared.update(kind="polygon", stroke=symbolizer.stroke, fill_opacity=fill.opacity)
        return fill.color, shared
    if isinstance(symbolizer, LineSymbolizer):
        stroke = symbolizer.stroke
        if stroke.linejoin or stroke.linecap or stroke.dasharray:
            raise NotRecognized(f"{what} line only carries color, width and opacity")
        shared.update(kind="line", stroke=None, fill_opacity=stroke.opacity, size=stroke.width)
        return stroke.color, shared
    if isinstance(symbolizer, PointSymbolizer):
        return _read_point(symbolizer.graphic, shared, what)
    raise NotRecognized(f"{what} needs a plain polygon fill, a line or a mark")


def _read_point(graphic: Graphic, shared: dict[str, Any], what: str) -> tuple[str, dict[str, Any]]:
    mark = graphic.symbol
    if not isinstance(mark, Mark) or not isinstance(mark.fill, Fill) or graphic.size is None:
        raise NotRecognized(f"{what} point needs a filled mark with a size")
    plain = graphic.rotation == 0 and graphic.opacity == 1
    if not plain or graphic.anchor is not None or graphic.displacement is not None:
        raise NotRecognized(f"{what} point carries no rotation, opacity, anchor or displacement")
    shared.update(
        kind="point",
        stroke=mark.stroke,
        fill_opacity=mark.fill.opacity,
        size=graphic.size,
        mark=mark.name,
    )
    return mark.fill.color, shared
