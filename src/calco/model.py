from __future__ import annotations

from dataclasses import dataclass, field

from calco.errors import InvalidModel
from calco.filters import FILTER_TYPES, Filter
from calco.symbolizers import (
    LineSymbolizer,
    PointSymbolizer,
    PolygonSymbolizer,
    Symbolizer,
    TextSymbolizer,
)
from calco.values import optional_number, optional_text, required_text, set_field

SYMBOLIZERS = (PolygonSymbolizer, LineSymbolizer, PointSymbolizer, TextSymbolizer)


@dataclass(frozen=True)
class ScaleRange:
    min: float | None = None
    max: float | None = None

    def __post_init__(self) -> None:
        low = optional_number(self.min, "ScaleRange.min")
        high = optional_number(self.max, "ScaleRange.max")
        if (low is not None and low < 0) or (high is not None and high <= 0):
            raise InvalidModel("scale denominators must be positive")
        if low is not None and high is not None and low >= high:
            raise InvalidModel("ScaleRange.min must be lower than ScaleRange.max")
        set_field(self, "min", low)
        set_field(self, "max", high)


@dataclass(frozen=True)
class Rule:
    symbolizers: tuple[Symbolizer, ...]
    name: str | None = None
    title: str | None = None
    abstract: str | None = None
    filter: Filter | None = None
    else_filter: bool = False
    scales: ScaleRange = ScaleRange()

    def __post_init__(self) -> None:
        if not isinstance(self.symbolizers, tuple | list) or not self.symbolizers:
            raise InvalidModel("Rule needs at least one symbolizer")
        if not all(isinstance(item, SYMBOLIZERS) for item in self.symbolizers):
            raise InvalidModel("Rule.symbolizers has a non-symbolizer item")
        set_field(self, "symbolizers", tuple(self.symbolizers))
        set_field(self, "name", optional_text(self.name, "Rule.name"))
        set_field(self, "title", optional_text(self.title, "Rule.title"))
        set_field(self, "abstract", optional_text(self.abstract, "Rule.abstract"))
        if self.filter is not None and not isinstance(self.filter, FILTER_TYPES):
            raise InvalidModel("Rule.filter must be a filter")
        if self.filter is not None and self.else_filter:
            raise InvalidModel("Rule cannot have both a filter and else_filter")
        if not isinstance(self.scales, ScaleRange):
            raise InvalidModel("Rule.scales must be a ScaleRange")


@dataclass(frozen=True)
class FeatureTypeStyle:
    rules: tuple[Rule, ...]
    name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.rules, tuple | list) or not self.rules:
            raise InvalidModel("FeatureTypeStyle needs at least one rule")
        if not all(isinstance(item, Rule) for item in self.rules):
            raise InvalidModel("FeatureTypeStyle.rules has a non-rule item")
        set_field(self, "rules", tuple(self.rules))
        set_field(self, "name", optional_text(self.name, "FeatureTypeStyle.name"))


@dataclass(frozen=True)
class UserStyle:
    styles: tuple[FeatureTypeStyle, ...]
    name: str | None = None
    title: str | None = None
    abstract: str | None = None
    is_default: bool = False
    unsupported: tuple[str, ...] = field(default=(), compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.styles, tuple | list) or not self.styles:
            raise InvalidModel("UserStyle needs at least one FeatureTypeStyle")
        if not all(isinstance(item, FeatureTypeStyle) for item in self.styles):
            raise InvalidModel("UserStyle.styles has a non-FeatureTypeStyle item")
        set_field(self, "styles", tuple(self.styles))
        for name in ("name", "title", "abstract"):
            set_field(self, name, optional_text(getattr(self, name), f"UserStyle.{name}"))
        set_field(self, "is_default", bool(self.is_default))
        set_field(self, "unsupported", tuple(self.unsupported))

    @property
    def rules(self) -> tuple[Rule, ...]:
        return tuple(rule for style in self.styles for rule in style.rules)


@dataclass(frozen=True)
class StyledLayer:
    name: str
    user_styles: tuple[UserStyle, ...] = ()
    named_style: str | None = None
    unsupported: tuple[str, ...] = field(default=(), compare=False)

    def __post_init__(self) -> None:
        set_field(self, "name", required_text(self.name, "StyledLayer.name"))
        if not isinstance(self.user_styles, tuple | list):
            raise InvalidModel("StyledLayer.user_styles must be a sequence")
        if not all(isinstance(item, UserStyle) for item in self.user_styles):
            raise InvalidModel("StyledLayer.user_styles has a non-UserStyle item")
        set_field(self, "user_styles", tuple(self.user_styles))
        named = None if self.named_style is None else required_text(self.named_style, "named_style")
        set_field(self, "named_style", named)
        if (named is None) == (not self.user_styles):
            raise InvalidModel("StyledLayer needs either user styles or a named_style, not both")
        set_field(self, "unsupported", tuple(self.unsupported))

    @property
    def rules(self) -> tuple[Rule, ...]:
        return tuple(rule for style in self.user_styles for rule in style.rules)

    def pick_style(self, name: str | None = None) -> UserStyle | None:
        if name is not None:
            return next((item for item in self.user_styles if item.name == name), None)
        defaults = [item for item in self.user_styles if item.is_default]
        if len(defaults) == 1:
            return defaults[0]
        return self.user_styles[0] if len(self.user_styles) == 1 else None


@dataclass(frozen=True)
class StyledLayerDescriptor:
    layers: tuple[StyledLayer, ...]
    unsupported: tuple[str, ...] = field(default=(), compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.layers, tuple | list) or not self.layers:
            raise InvalidModel("StyledLayerDescriptor needs at least one layer")
        if not all(isinstance(item, StyledLayer) for item in self.layers):
            raise InvalidModel("StyledLayerDescriptor.layers has a non-layer item")
        set_field(self, "layers", tuple(self.layers))
        set_field(self, "unsupported", tuple(self.unsupported))

    @property
    def all_unsupported(self) -> tuple[str, ...]:
        return self.unsupported + tuple(
            note
            for layer in self.layers
            for note in (
                *layer.unsupported,
                *(item for style in layer.user_styles for item in style.unsupported),
            )
        )
