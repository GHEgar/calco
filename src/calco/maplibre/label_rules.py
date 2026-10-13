from __future__ import annotations

from dataclasses import dataclass

from calco.filters import Filter
from calco.model import Rule, StyledLayer, StyledLayerDescriptor
from calco.symbolizers import TextSymbolizer


@dataclass(frozen=True)
class LabelRule:
    layer: str
    index: int
    rule: Rule
    text: TextSymbolizer
    siblings: tuple[Filter | None, ...] = ()


def read_label_rules(
    source: StyledLayerDescriptor | StyledLayer, style: str | None = None
) -> list[LabelRule]:
    layers = source.layers if isinstance(source, StyledLayerDescriptor) else (source,)
    found: list[LabelRule] = []
    for layer in layers:
        index = 0
        user_style = layer.pick_style(style)
        if user_style is None:
            continue
        for style_entry in user_style.styles:
            siblings = tuple(rule.filter for rule in style_entry.rules if not rule.else_filter)
            for rule in style_entry.rules:
                for symbolizer in rule.symbolizers:
                    if isinstance(symbolizer, TextSymbolizer):
                        found.append(LabelRule(layer.name, index, rule, symbolizer, siblings))
                        index += 1
    return found
