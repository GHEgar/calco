from __future__ import annotations

from dataclasses import dataclass

from calco.errors import InvalidModel, NotRecognized
from calco.expressions import Expression
from calco.filters import IsNull
from calco.model import Rule, ScaleRange
from calco.symbolizers import Fill, Graphic, GraphicFill, Mark, PolygonSymbolizer, Stroke
from calco.values import (
    clean_text,
    in_range,
    non_negative,
    required_text,
    set_field,
    to_color,
)


@dataclass(frozen=True)
class Hatch:
    mark: str = "shape://times"
    color: str = "#7A7A7A"
    size: float = 7
    width: float = 1
    opacity: float = 1

    def __post_init__(self) -> None:
        set_field(self, "mark", required_text(self.mark, "Hatch.mark"))
        set_field(self, "color", to_color(self.color, "Hatch.color"))
        set_field(self, "size", non_negative(self.size, "Hatch.size"))
        set_field(self, "width", non_negative(self.width, "Hatch.width"))
        set_field(self, "opacity", in_range(self.opacity, "Hatch.opacity", 0, 1))

    def to_fill(self) -> GraphicFill:
        stroke = Stroke(self.color, self.width, self.opacity)
        return GraphicFill(Graphic(Mark(self.mark, fill=None, stroke=stroke), size=self.size))

    @classmethod
    def from_fill(cls, fill: GraphicFill) -> Hatch:
        graphic = fill.graphic
        mark = graphic.symbol
        if not isinstance(mark, Mark) or mark.fill is not None or mark.stroke is None:
            raise NotRecognized("a hatch is a Mark with a stroke and no fill")
        stroke = mark.stroke
        if stroke.linejoin or stroke.linecap or stroke.dasharray:
            raise NotRecognized("hatch stroke only carries color, width and opacity")
        if graphic.size is None or graphic.rotation != 0 or graphic.opacity != 1:
            raise NotRecognized("hatch graphic needs a size, no rotation and full opacity")
        return cls(mark.name, stroke.color, graphic.size, stroke.width, stroke.opacity)


def as_fill(value: Fill | Hatch | None) -> Fill | GraphicFill | None:
    return value.to_fill() if isinstance(value, Hatch) else value


def from_fill(value: Fill | GraphicFill | None) -> Fill | Hatch | None:
    return Hatch.from_fill(value) if isinstance(value, GraphicFill) else value


@dataclass(frozen=True)
class NullStyle:
    title: str | None = "No data"
    background: Fill | None = Fill("#FFFFFF")
    hatch: Hatch | None = Hatch()
    stroke: Stroke | None = Stroke("#7A7A7A", 0.35)

    def __post_init__(self) -> None:
        if self.title is not None:
            set_field(self, "title", clean_text(self.title, "NullStyle.title"))
        if self.background is not None and not isinstance(self.background, Fill):
            raise InvalidModel("NullStyle.background must be a Fill")
        if self.hatch is not None and not isinstance(self.hatch, Hatch):
            raise InvalidModel("NullStyle.hatch must be a Hatch")
        if self.stroke is not None and not isinstance(self.stroke, Stroke):
            raise InvalidModel("NullStyle.stroke must be a Stroke")
        if self.background is None and self.hatch is None and self.stroke is None:
            raise InvalidModel("NullStyle needs a background, a hatch or a stroke")

    def to_rule(self, attribute: str, geometry: Expression | None, scales: ScaleRange) -> Rule:
        symbolizers: list[PolygonSymbolizer] = []
        if self.hatch is not None:
            if self.background is not None:
                symbolizers.append(PolygonSymbolizer(self.background, None, geometry))
            symbolizers.append(PolygonSymbolizer(self.hatch.to_fill(), self.stroke, geometry))
        else:
            symbolizers.append(PolygonSymbolizer(self.background, self.stroke, geometry))
        return Rule(
            tuple(symbolizers),
            name="null",
            title=self.title,
            filter=IsNull(attribute),
            scales=scales,
        )

    @classmethod
    def from_rule(cls, rule: Rule) -> tuple[NullStyle, Expression | None]:
        if rule.abstract is not None:
            raise NotRecognized("the null rule abstract is not part of the recipe")
        parts = rule.symbolizers
        if not all(isinstance(item, PolygonSymbolizer) for item in parts) or len(parts) > 2:
            raise NotRecognized("the null rule holds one or two PolygonSymbolizers")
        polygons = [item for item in parts if isinstance(item, PolygonSymbolizer)]
        if len({item.geometry for item in polygons}) != 1:
            raise NotRecognized("the null rule symbolizers use different geometries")
        last = polygons[-1]
        if len(polygons) == 2:
            first = polygons[0]
            if not isinstance(first.fill, Fill) or first.stroke is not None:
                raise NotRecognized("the null background is a plain fill without stroke")
            if not isinstance(last.fill, GraphicFill):
                raise NotRecognized("the second null symbolizer must be the hatch")
            style = cls(rule.title, first.fill, Hatch.from_fill(last.fill), last.stroke)
        elif isinstance(last.fill, GraphicFill):
            style = cls(rule.title, None, Hatch.from_fill(last.fill), last.stroke)
        else:
            style = cls(rule.title, last.fill, None, last.stroke)
        return style, last.geometry
