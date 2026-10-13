from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from calco.errors import InvalidModel, NotRecognized
from calco.expressions import Expression, optional_expression
from calco.filters import Compare, IsNull
from calco.model import Rule, ScaleRange, StyledLayer
from calco.recipes.common import build_layer, only, single_style, split_text_rules
from calco.recipes.fills import NullStyle, match_null
from calco.recipes.label import Label
from calco.symbolizers import Fill, PolygonSymbolizer, Stroke
from calco.values import (
    Number,
    in_range,
    literal_value,
    optional_text,
    required_text,
    set_field,
    to_color,
)


@dataclass(frozen=True)
class Category:
    value: Number | str
    color: str
    title: str | None = None

    def __post_init__(self) -> None:
        set_field(self, "value", literal_value(self.value, "Category.value"))
        set_field(self, "color", to_color(self.color, "Category.color"))
        set_field(self, "title", optional_text(self.title, "Category.title"))


@dataclass(frozen=True)
class Other:
    color: str
    title: str | None = None

    def __post_init__(self) -> None:
        set_field(self, "color", to_color(self.color, "Other.color"))
        set_field(self, "title", optional_text(self.title, "Other.title"))


@dataclass(frozen=True)
class Categories:
    layer: str
    attribute: str
    categories: tuple[Category, ...]
    other: Other | None = None
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
        set_field(self, "layer", required_text(self.layer, "Categories.layer"))
        set_field(self, "attribute", required_text(self.attribute, "Categories.attribute"))
        items = self.categories
        if not isinstance(items, tuple | list) or not items:
            raise InvalidModel("Categories.categories needs at least one Category")
        if not all(isinstance(item, Category) for item in items):
            raise InvalidModel("Categories.categories has a non-Category item")
        if len({item.value for item in items}) != len(items):
            raise InvalidModel("category values must be unique")
        set_field(self, "categories", tuple(items))
        set_field(self, "fill_opacity", in_range(self.fill_opacity, "fill_opacity", 0, 1))
        checks = (("other", Other), ("stroke", Stroke), ("null", NullStyle), ("label", Label))
        for name, kind in checks:
            value = getattr(self, name)
            if value is not None and not isinstance(value, kind):
                raise InvalidModel(f"Categories.{name} must be a {kind.__name__}")
        optional_expression(self.geometry, "Categories.geometry")
        if not isinstance(self.scales, ScaleRange):
            raise InvalidModel("Categories.scales must be a ScaleRange")
        for name in ("title", "abstract", "style_name"):
            set_field(self, name, optional_text(getattr(self, name), f"Categories.{name}"))

    @classmethod
    def from_values(
        cls,
        layer: str,
        attribute: str,
        values: Sequence[Number | str],
        colors: Sequence[str],
        titles: Sequence[str | None] | None = None,
        **options: Any,
    ) -> Categories:
        if len(colors) != len(values) or (titles is not None and len(titles) != len(values)):
            raise InvalidModel("values, colors and titles must have the same length")
        names = list(titles) if titles is not None else [None] * len(values)
        items = tuple(map(Category, values, colors, names))
        return cls(layer, attribute, items, **options)

    def _symbolizer(self, color: str) -> PolygonSymbolizer:
        return PolygonSymbolizer(Fill(color, self.fill_opacity), self.stroke, self.geometry)

    def to_layer(self) -> StyledLayer:
        rules = [
            Rule(
                (self._symbolizer(item.color),),
                name=f"category-{index + 1}",
                title=item.title,
                filter=Compare(self.attribute, "=", item.value),
                scales=self.scales,
            )
            for index, item in enumerate(self.categories)
        ]
        if self.null is not None:
            rules.append(self.null.to_rule(self.attribute, self.geometry, self.scales))
        if self.other is not None:
            rules.append(
                Rule(
                    (self._symbolizer(self.other.color),),
                    name="other",
                    title=self.other.title,
                    else_filter=True,
                    scales=self.scales,
                )
            )
        if self.label is not None:
            rules.append(self.label.to_rule())
        return build_layer(
            self.layer, rules, style_name=self.style_name, title=self.title, abstract=self.abstract
        )

    @classmethod
    def from_layer(cls, layer: StyledLayer, style: str | None = None) -> Categories:
        user_style, rules = single_style(layer, style)
        body, text_rule = split_text_rules(rules)
        nulls = [rule for rule in body if isinstance(rule.filter, IsNull)]
        others = [rule for rule in body if rule.else_filter]
        values = [rule for rule in body if rule not in nulls and rule not in others]
        if len(nulls) > 1 or len(others) > 1 or not values:
            raise NotRecognized("expected value rules, at most one null rule and one else rule")
        attribute: str | None = None
        shared: dict[str, Any] | None = None
        found: list[tuple[Number | str, str, str | None]] = []
        for rule in [*values, *others]:
            if rule.abstract is not None:
                raise NotRecognized("category rules carry no abstract")
            if not rule.else_filter:
                compare = rule.filter
                if not isinstance(compare, Compare) or compare.operator != "=":
                    raise NotRecognized("category rules filter with a single equality")
                if attribute not in (None, compare.property):
                    raise NotRecognized("category rules use different attributes")
                attribute = compare.property
            polygon = only(rule.symbolizers, PolygonSymbolizer, "a category rule")
            assert isinstance(polygon, PolygonSymbolizer)
            if not isinstance(polygon.fill, Fill):
                raise NotRecognized("category rules need a plain fill")
            current = {
                "stroke": polygon.stroke,
                "fill_opacity": polygon.fill.opacity,
                "geometry": polygon.geometry,
                "scales": rule.scales,
            }
            if shared is not None and current != shared:
                raise NotRecognized("category rules differ in stroke, opacity, geometry or scales")
            shared = current
            value = rule.filter.value if isinstance(rule.filter, Compare) else ""
            found.append((value, polygon.fill.color, rule.title))
        assert attribute is not None and shared is not None
        other = Other(*found.pop()[1:]) if others else None
        null = (
            match_null(nulls[0], attribute, shared["scales"], shared["geometry"]) if nulls else None
        )
        try:
            return cls(
                layer.name,
                attribute,
                tuple(Category(*item) for item in found),
                other,
                null=null,
                label=None if text_rule is None else Label.from_rule(text_rule),
                title=user_style.title,
                abstract=user_style.abstract,
                style_name=user_style.name,
                **shared,
            )
        except InvalidModel as exc:
            raise NotRecognized(str(exc)) from exc
