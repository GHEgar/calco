from __future__ import annotations

from dataclasses import dataclass, field

from calco.errors import InvalidModel, NotRecognized
from calco.expressions import Expression, as_expressions, optional_expression
from calco.model import Rule, ScaleRange
from calco.recipes.common import only
from calco.symbolizers import (
    Fill,
    Font,
    Halo,
    LinePlacement,
    PointPlacement,
    TextSymbolizer,
    vendor_options,
)
from calco.values import set_field


@dataclass(frozen=True)
class Label:
    content: tuple[Expression, ...] | Expression
    font: Font = Font()
    fill: Fill = Fill("#000000")
    halo: Halo | None = None
    placement: PointPlacement | LinePlacement = PointPlacement()
    geometry: Expression | None = None
    vendor_options: dict[str, str] = field(default_factory=dict)
    scales: ScaleRange = ScaleRange()

    def __post_init__(self) -> None:
        set_field(self, "content", as_expressions(self.content, "Label.content"))
        if not isinstance(self.font, Font) or not isinstance(self.fill, Fill):
            raise InvalidModel("Label.font and Label.fill are required")
        if self.halo is not None and not isinstance(self.halo, Halo):
            raise InvalidModel("Label.halo must be a Halo")
        if not isinstance(self.placement, PointPlacement | LinePlacement):
            raise InvalidModel("Label.placement must be a PointPlacement or a LinePlacement")
        optional_expression(self.geometry, "Label.geometry")
        set_field(self, "vendor_options", vendor_options(self.vendor_options))
        if not isinstance(self.scales, ScaleRange):
            raise InvalidModel("Label.scales must be a ScaleRange")

    def to_rule(self) -> Rule:
        symbolizer = TextSymbolizer(
            label=self.content,
            font=self.font,
            placement=self.placement,
            halo=self.halo,
            fill=self.fill,
            geometry=self.geometry,
            vendor_options=self.vendor_options,
        )
        return Rule((symbolizer,), name="label", scales=self.scales)

    @classmethod
    def from_rule(cls, rule: Rule) -> Label:
        if rule.filter is not None or rule.else_filter:
            raise NotRecognized("a label rule with a filter is not part of the recipe")
        if rule.title is not None or rule.abstract is not None:
            raise NotRecognized("label rule title and abstract are not part of the recipe")
        text = only(rule.symbolizers, TextSymbolizer, "the label rule")
        assert isinstance(text, TextSymbolizer)
        return cls(
            content=text.label,
            font=text.font or Font(),
            fill=text.fill or Fill("#000000"),
            halo=text.halo,
            placement=text.placement or PointPlacement(0, 0.5),
            geometry=text.geometry,
            vendor_options=text.vendor_options,
            scales=rule.scales,
        )
