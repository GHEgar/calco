from __future__ import annotations

from dataclasses import dataclass

from calco.errors import InvalidModel, NotRecognized
from calco.expressions import Expression, optional_expression
from calco.model import Rule, ScaleRange, StyledLayer, UserStyle
from calco.recipes.common import build_layer, only, single_style, split_text_rules
from calco.recipes.fills import Hatch, as_fill, from_fill
from calco.recipes.label import Label
from calco.symbolizers import (
    Fill,
    Graphic,
    LineSymbolizer,
    PointSymbolizer,
    PolygonSymbolizer,
    Stroke,
    Symbolizer,
)
from calco.values import optional_text, required_text, set_field

HEADER = ("title", "abstract", "style_name", "rule_name", "rule_title")


def _check_common(target: Polygon | Point | Line, kind: str) -> None:
    set_field(target, "layer", required_text(target.layer, f"{kind}.layer"))
    label = target.label
    if label is not None and not isinstance(label, Label):
        raise InvalidModel(f"{kind}.label must be a Label")
    optional_expression(target.geometry, f"{kind}.geometry")
    if not isinstance(target.scales, ScaleRange):
        raise InvalidModel(f"{kind}.scales must be a ScaleRange")
    for name in HEADER:
        set_field(target, name, optional_text(getattr(target, name), f"{kind}.{name}"))


def _layer(target: Polygon | Point | Line, *symbolizers: Symbolizer) -> StyledLayer:
    rules = [
        Rule(
            symbolizers,
            name=target.rule_name,
            title=target.rule_title,
            scales=target.scales,
        )
    ]
    if target.label is not None:
        rules.append(target.label.to_rule())
    return build_layer(
        target.layer,
        rules,
        style_name=target.style_name,
        title=target.title,
        abstract=target.abstract,
    )


def _main_rule(layer: StyledLayer, style: str | None) -> tuple[UserStyle, Rule, Label | None]:
    user_style, rules = single_style(layer, style)
    body, text_rule = split_text_rules(rules)
    if len(body) != 1:
        raise NotRecognized("expected one symbol rule and an optional label rule")
    rule = body[0]
    if rule.filter is not None or rule.else_filter or rule.abstract is not None:
        raise NotRecognized("the symbol rule carries no filter and no abstract")
    return user_style, rule, None if text_rule is None else Label.from_rule(text_rule)


def _header(user_style: UserStyle, rule: Rule) -> dict[str, str | None]:
    return {
        "title": user_style.title,
        "abstract": user_style.abstract,
        "style_name": user_style.name,
        "rule_name": rule.name,
        "rule_title": rule.title,
    }


@dataclass(frozen=True)
class Polygon:
    layer: str
    fill: Fill | Hatch | None = Fill()
    stroke: Stroke | None = Stroke()
    label: Label | None = None
    geometry: Expression | None = None
    scales: ScaleRange = ScaleRange()
    title: str | None = None
    abstract: str | None = None
    style_name: str | None = None
    rule_name: str | None = None
    rule_title: str | None = None

    def __post_init__(self) -> None:
        _check_common(self, "Polygon")
        if self.fill is not None and not isinstance(self.fill, Fill | Hatch):
            raise InvalidModel("Polygon.fill must be a Fill or a Hatch")
        if self.stroke is not None and not isinstance(self.stroke, Stroke):
            raise InvalidModel("Polygon.stroke must be a Stroke")
        if self.fill is None and self.stroke is None:
            raise InvalidModel("Polygon needs a fill or a stroke")

    def to_layer(self) -> StyledLayer:
        return _layer(self, PolygonSymbolizer(as_fill(self.fill), self.stroke, self.geometry))

    @classmethod
    def from_layer(cls, layer: StyledLayer, style: str | None = None) -> Polygon:
        user_style, rule, label = _main_rule(layer, style)
        polygon = only(rule.symbolizers, PolygonSymbolizer, "the polygon rule")
        assert isinstance(polygon, PolygonSymbolizer)
        try:
            return cls(
                layer.name,
                from_fill(polygon.fill),
                polygon.stroke,
                label,
                polygon.geometry,
                rule.scales,
                **_header(user_style, rule),
            )
        except InvalidModel as exc:
            raise NotRecognized(str(exc)) from exc


@dataclass(frozen=True)
class Point:
    layer: str
    graphic: Graphic = Graphic()
    label: Label | None = None
    geometry: Expression | None = None
    scales: ScaleRange = ScaleRange()
    title: str | None = None
    abstract: str | None = None
    style_name: str | None = None
    rule_name: str | None = None
    rule_title: str | None = None

    def __post_init__(self) -> None:
        _check_common(self, "Point")
        if not isinstance(self.graphic, Graphic):
            raise InvalidModel("Point.graphic must be a Graphic")

    def to_layer(self) -> StyledLayer:
        return _layer(self, PointSymbolizer(self.graphic, self.geometry))

    @classmethod
    def from_layer(cls, layer: StyledLayer, style: str | None = None) -> Point:
        user_style, rule, label = _main_rule(layer, style)
        point = only(rule.symbolizers, PointSymbolizer, "the point rule")
        assert isinstance(point, PointSymbolizer)
        return cls(
            layer.name,
            point.graphic,
            label,
            point.geometry,
            rule.scales,
            **_header(user_style, rule),
        )


@dataclass(frozen=True)
class Line:
    layer: str
    strokes: tuple[Stroke, ...] | Stroke = Stroke()
    label: Label | None = None
    geometry: Expression | None = None
    scales: ScaleRange = ScaleRange()
    title: str | None = None
    abstract: str | None = None
    style_name: str | None = None
    rule_name: str | None = None
    rule_title: str | None = None

    def __post_init__(self) -> None:
        _check_common(self, "Line")
        strokes = (self.strokes,) if isinstance(self.strokes, Stroke) else self.strokes
        if not isinstance(strokes, tuple | list) or not strokes:
            raise InvalidModel("Line.strokes needs at least one Stroke")
        if not all(isinstance(item, Stroke) for item in strokes):
            raise InvalidModel("Line.strokes has a non-Stroke item")
        set_field(self, "strokes", tuple(strokes))

    @property
    def stroke_list(self) -> tuple[Stroke, ...]:
        return self.strokes if isinstance(self.strokes, tuple) else (self.strokes,)

    def to_layer(self) -> StyledLayer:
        return _layer(self, *(LineSymbolizer(item, self.geometry) for item in self.stroke_list))

    @classmethod
    def from_layer(cls, layer: StyledLayer, style: str | None = None) -> Line:
        user_style, rule, label = _main_rule(layer, style)
        lines = [item for item in rule.symbolizers if isinstance(item, LineSymbolizer)]
        if len(lines) != len(rule.symbolizers):
            raise NotRecognized("the line rule holds only LineSymbolizers")
        if len({item.geometry for item in lines}) != 1:
            raise NotRecognized("the line symbolizers use different geometries")
        return cls(
            layer.name,
            tuple(item.stroke for item in lines),
            label,
            lines[0].geometry,
            rule.scales,
            **_header(user_style, rule),
        )
