from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from calco.errors import InvalidModel, NotRecognized
from calco.expressions import Expression, optional_expression
from calco.filters import Compare, Filter, IsNull, Or
from calco.model import Rule, ScaleRange, StyledLayer
from calco.recipes.common import build_layer, single_style, split_text_rules
from calco.recipes.fills import NullStyle, match_null
from calco.recipes.label import Label
from calco.recipes.swatch import (
    DEFAULT_MARK,
    DEFAULT_SIZE,
    Kind,
    check_swatch,
    class_symbolizer,
    read_class_symbolizer,
)
from calco.symbolizers import Stroke
from calco.values import Number, literal_value, optional_text, required_text, set_field, to_color

Value = Number | str


@dataclass(frozen=True)
class Category:
    value: Value | tuple[Value, ...]
    color: str
    title: str | None = None

    def __post_init__(self) -> None:
        raw = self.value if isinstance(self.value, tuple | list) else (self.value,)
        values = tuple(literal_value(item, "Category.value") for item in raw)
        if not values or len(set(values)) != len(values):
            raise InvalidModel("Category needs one or more distinct values")
        set_field(self, "value", values[0] if len(values) == 1 else values)
        set_field(self, "color", to_color(self.color, "Category.color"))
        set_field(self, "title", optional_text(self.title, "Category.title"))

    @property
    def values(self) -> tuple[Value, ...]:
        return self.value if isinstance(self.value, tuple) else (self.value,)

    def filter(self, attribute: str) -> Filter:
        parts = tuple(Compare(attribute, "=", item) for item in self.values)
        return parts[0] if len(parts) == 1 else Or(parts)


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
    kind: Kind = "polygon"
    size: float = DEFAULT_SIZE
    mark: str = DEFAULT_MARK

    def __post_init__(self) -> None:
        set_field(self, "layer", required_text(self.layer, "Categories.layer"))
        set_field(self, "attribute", required_text(self.attribute, "Categories.attribute"))
        items = self.categories
        if not isinstance(items, tuple | list) or not items:
            raise InvalidModel("Categories.categories needs at least one Category")
        if not all(isinstance(item, Category) for item in items):
            raise InvalidModel("Categories.categories has a non-Category item")
        every = [value for item in items for value in item.values]
        if len(set(every)) != len(every):
            raise InvalidModel("a value belongs to more than one category")
        set_field(self, "categories", tuple(items))
        check_swatch(self, "Categories")
        if self.null is not None and self.kind != "polygon":
            raise InvalidModel("the null rule is only available for polygons")
        for name, kind in (("other", Other), ("null", NullStyle), ("label", Label)):
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
        values: Sequence[Value | tuple[Value, ...]],
        colors: Sequence[str],
        titles: Sequence[str | None] | None = None,
        **options: Any,
    ) -> Categories:
        if len(colors) != len(values) or (titles is not None and len(titles) != len(values)):
            raise InvalidModel("values, colors and titles must have the same length")
        names = list(titles) if titles is not None else [None] * len(values)
        items = tuple(map(Category, values, colors, names))
        return cls(layer, attribute, items, **options)

    def to_layer(self) -> StyledLayer:
        rules = [
            Rule(
                (class_symbolizer(self, item.color),),
                name=f"category-{index + 1}",
                title=item.title,
                filter=item.filter(self.attribute),
                scales=self.scales,
            )
            for index, item in enumerate(self.categories)
        ]
        if self.null is not None:
            rules.append(self.null.to_rule(self.attribute, self.geometry, self.scales))
        if self.other is not None:
            rules.append(
                Rule(
                    (class_symbolizer(self, self.other.color),),
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
        valued = [rule for rule in body if rule not in nulls and rule not in others]
        if len(nulls) > 1 or len(others) > 1 or not valued:
            raise NotRecognized("expected value rules, at most one null rule and one else rule")
        attribute: str | None = None
        shared: dict[str, Any] | None = None
        found: list[tuple[tuple[Value, ...], str, str | None]] = []
        for rule in [*valued, *others]:
            if rule.abstract is not None:
                raise NotRecognized("category rules carry no abstract")
            prop, values = _equalities(rule.filter) if not rule.else_filter else (attribute, ())
            if attribute not in (None, prop):
                raise NotRecognized("category rules use different attributes")
            attribute = prop
            color, current = read_class_symbolizer(rule, "a category rule")
            if shared is not None and current != shared:
                raise NotRecognized("category rules differ in symbol, opacity, geometry or scales")
            shared = current
            found.append((values, color, rule.title))
        if attribute is None or shared is None:
            raise NotRecognized("no category rule names an attribute")
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


def _equalities(rule_filter: Filter | None) -> tuple[str, tuple[Value, ...]]:
    parts = rule_filter.operands if isinstance(rule_filter, Or) else (rule_filter,)
    compares = [part for part in parts if isinstance(part, Compare) and part.operator == "="]
    if len(compares) != len(parts) or len({part.property for part in compares}) != 1:
        raise NotRecognized("category rules filter with equalities on a single attribute")
    return compares[0].property, tuple(part.value for part in compares)
