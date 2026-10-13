from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from calco.classify import Classification
from calco.errors import InvalidModel, NotRecognized
from calco.expressions import Expression, optional_expression
from calco.filters import And, Compare, Filter, IsNull
from calco.model import Rule, ScaleRange, StyledLayer
from calco.recipes.common import build_layer, only, single_style, split_text_rules
from calco.recipes.fills import NullStyle, match_null
from calco.recipes.label import Label
from calco.symbolizers import Fill, PolygonSymbolizer, Stroke
from calco.values import (
    Number,
    in_range,
    optional_number,
    optional_text,
    parse_number,
    required_text,
    set_field,
    to_color,
)


@dataclass(frozen=True)
class RangeClass:
    lower: float | None
    upper: float | None
    color: str
    title: str | None = None

    def __post_init__(self) -> None:
        set_field(self, "lower", optional_number(self.lower, "RangeClass.lower"))
        set_field(self, "upper", optional_number(self.upper, "RangeClass.upper"))
        set_field(self, "color", to_color(self.color, "RangeClass.color"))
        set_field(self, "title", optional_text(self.title, "RangeClass.title"))
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise InvalidModel(f"class lower {self.lower} must not exceed upper {self.upper}")


@dataclass(frozen=True)
class Choropleth:
    layer: str
    attribute: str
    classes: tuple[RangeClass, ...]
    stroke: Stroke | None = Stroke("#FFFFFF", 0.35)
    fill_opacity: float = 1
    null: NullStyle | None = None
    label: Label | None = None
    geometry: Expression | None = None
    scales: ScaleRange = ScaleRange()
    title: str | None = None
    abstract: str | None = None
    style_name: str | None = None

    def __post_init__(self) -> None:
        set_field(self, "layer", required_text(self.layer, "Choropleth.layer"))
        set_field(self, "attribute", required_text(self.attribute, "Choropleth.attribute"))
        set_field(self, "classes", _check_classes(self.classes))
        set_field(self, "fill_opacity", in_range(self.fill_opacity, "fill_opacity", 0, 1))
        for name, kind in (("stroke", Stroke), ("null", NullStyle), ("label", Label)):
            value = getattr(self, name)
            if value is not None and not isinstance(value, kind):
                raise InvalidModel(f"Choropleth.{name} must be a {kind.__name__}")
        optional_expression(self.geometry, "Choropleth.geometry")
        if not isinstance(self.scales, ScaleRange):
            raise InvalidModel("Choropleth.scales must be a ScaleRange")
        for name in ("title", "abstract", "style_name"):
            set_field(self, name, optional_text(getattr(self, name), f"Choropleth.{name}"))

    @classmethod
    def from_breaks(
        cls,
        layer: str,
        attribute: str,
        breaks: Sequence[float | None],
        colors: Sequence[str],
        titles: Sequence[str | None] | None = None,
        **options: Any,
    ) -> Choropleth:
        count = len(breaks) - 1
        if count < 1 or len(colors) != count or (titles is not None and len(titles) != count):
            raise InvalidModel("breaks needs n+1 values for n colors and n titles")
        names = list(titles) if titles is not None else [None] * count
        classes = tuple(
            RangeClass(breaks[index], breaks[index + 1], colors[index], names[index])
            for index in range(count)
        )
        return cls(layer, attribute, classes, **options)

    @classmethod
    def from_classification(
        cls,
        layer: str,
        attribute: str,
        classification: Classification,
        colors: Sequence[str],
        titles: Sequence[str | None] | None = None,
        **options: Any,
    ) -> Choropleth:
        if classification.actual < 1:
            raise InvalidModel("the classification has no classes")
        return cls.from_breaks(layer, attribute, classification.breaks, colors, titles, **options)

    @property
    def breaks(self) -> tuple[float | None, ...]:
        return (self.classes[0].lower, *(item.upper for item in self.classes))

    def to_layer(self) -> StyledLayer:
        last = len(self.classes) - 1
        rules = [
            Rule(
                (
                    PolygonSymbolizer(
                        Fill(item.color, self.fill_opacity), self.stroke, self.geometry
                    ),
                ),
                name=f"class-{index + 1}",
                title=item.title,
                filter=_range_filter(self.attribute, item, index == last),
                scales=self.scales,
            )
            for index, item in enumerate(self.classes)
        ]
        if self.null is not None:
            rules.append(self.null.to_rule(self.attribute, self.geometry, self.scales))
        if self.label is not None:
            rules.append(self.label.to_rule())
        return build_layer(
            self.layer, rules, style_name=self.style_name, title=self.title, abstract=self.abstract
        )

    @classmethod
    def from_layer(cls, layer: StyledLayer, style: str | None = None) -> Choropleth:
        user_style, rules = single_style(layer, style)
        body, text_rule = split_text_rules(rules)
        null_rules = [rule for rule in body if isinstance(rule.filter, IsNull)]
        range_rules = [rule for rule in body if not isinstance(rule.filter, IsNull)]
        if len(null_rules) > 1:
            raise NotRecognized("more than one null rule")
        if not range_rules:
            raise NotRecognized("no range rules")
        attribute, classes, shared = _read_classes(range_rules)
        null = None
        if null_rules:
            null = match_null(null_rules[0], attribute, shared["scales"], shared["geometry"])
        try:
            return cls(
                layer.name,
                attribute,
                classes,
                null=null,
                label=None if text_rule is None else Label.from_rule(text_rule),
                title=user_style.title,
                abstract=user_style.abstract,
                style_name=user_style.name,
                **shared,
            )
        except InvalidModel as exc:
            raise NotRecognized(str(exc)) from exc


def _check_classes(value: object) -> tuple[RangeClass, ...]:
    if not isinstance(value, tuple | list) or not value:
        raise InvalidModel("Choropleth.classes needs at least one RangeClass")
    if not all(isinstance(item, RangeClass) for item in value):
        raise InvalidModel("Choropleth.classes has a non-RangeClass item")
    classes: tuple[RangeClass, ...] = tuple(value)
    for index, item in enumerate(classes):
        if item.lower is None and index > 0:
            raise InvalidModel("only the first class may have an open lower bound")
        if item.upper is None and index < len(classes) - 1:
            raise InvalidModel("only the last class may have an open upper bound")
        last = index == len(classes) - 1
        if not last and item.lower is not None and item.lower == item.upper:
            raise InvalidModel(f"class {index + 1} is empty; only the last class may be [x, x]")
        if index > 0 and classes[index - 1].upper != item.lower:
            raise InvalidModel(f"class {index + 1} does not start where class {index} ends")
    if len(classes) == 1 and classes[0].lower is None and classes[0].upper is None:
        raise InvalidModel("a single class needs at least one bound")
    return classes


def _range_filter(attribute: str, item: RangeClass, last: bool) -> Filter:
    parts: list[Filter] = []
    if item.lower is not None:
        parts.append(Compare(attribute, ">=", item.lower))
    if item.upper is not None:
        parts.append(Compare(attribute, "<=" if last else "<", item.upper))
    return parts[0] if len(parts) == 1 else And(tuple(parts))


def _bounds(rule_filter: Filter | None) -> tuple[str, Number | None, Number | None, str | None]:
    parts = rule_filter.operands if isinstance(rule_filter, And) else (rule_filter,)
    if not 1 <= len(parts) <= 2 or not all(isinstance(part, Compare) for part in parts):
        raise NotRecognized("range rules filter with >= and < (or <= on the last class)")
    compares = [part for part in parts if isinstance(part, Compare)]
    if len({part.property for part in compares}) != 1:
        raise NotRecognized("a range rule compares two attributes")
    lower = [part for part in compares if part.operator == ">="]
    upper = [part for part in compares if part.operator in ("<", "<=")]
    if len(lower) + len(upper) != len(compares) or len(lower) > 1 or len(upper) > 1:
        raise NotRecognized("range rules use >= for the lower bound and < or <= for the upper")
    values = [_as_number(part.value) for part in compares]
    if any(value is None for value in values):
        raise NotRecognized("range bounds must be numbers")
    low = _as_number(lower[0].value) if lower else None
    high = _as_number(upper[0].value) if upper else None
    assert not isinstance(low, str) and not isinstance(high, str)
    return compares[0].property, low, high, upper[0].operator if upper else None


def _read_classes(rules: list[Rule]) -> tuple[str, tuple[RangeClass, ...], dict[str, Any]]:
    attribute: str | None = None
    classes: list[RangeClass] = []
    shared: dict[str, Any] | None = None
    for index, rule in enumerate(rules):
        if rule.else_filter or rule.abstract is not None:
            raise NotRecognized("range rules carry no else filter and no abstract")
        prop, low, high, operator = _bounds(rule.filter)
        if attribute not in (None, prop):
            raise NotRecognized("range rules use different attributes")
        attribute = prop
        is_last = index == len(rules) - 1
        if operator is not None and operator != ("<=" if is_last else "<"):
            raise NotRecognized("only the last class closes its upper bound with <=")
        polygon = only(rule.symbolizers, PolygonSymbolizer, "a range rule")
        assert isinstance(polygon, PolygonSymbolizer)
        if not isinstance(polygon.fill, Fill):
            raise NotRecognized("range rules need a plain fill")
        current = {
            "stroke": polygon.stroke,
            "fill_opacity": polygon.fill.opacity,
            "geometry": polygon.geometry,
            "scales": rule.scales,
        }
        if shared is not None and current != shared:
            raise NotRecognized("range rules differ in stroke, opacity, geometry or scales")
        shared = current
        try:
            classes.append(RangeClass(low, high, polygon.fill.color, rule.title))
        except InvalidModel as exc:
            raise NotRecognized(str(exc)) from exc
    assert attribute is not None and shared is not None
    return attribute, tuple(classes), shared


def _as_number(value: Number | str) -> Number | None:
    return parse_number(value) if isinstance(value, str) else value
