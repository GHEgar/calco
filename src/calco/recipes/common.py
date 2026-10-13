from __future__ import annotations

from calco.errors import NotRecognized
from calco.model import FeatureTypeStyle, Rule, StyledLayer, UserStyle
from calco.symbolizers import Symbolizer, TextSymbolizer


def build_layer(
    layer: str,
    rules: list[Rule],
    *,
    style_name: str | None,
    title: str | None,
    abstract: str | None,
) -> StyledLayer:
    user_style = UserStyle(
        (FeatureTypeStyle(tuple(rules)),), name=style_name, title=title, abstract=abstract
    )
    return StyledLayer(layer, (user_style,))


def single_style(layer: StyledLayer, style: str | None) -> tuple[UserStyle, tuple[Rule, ...]]:
    if layer.named_style is not None:
        raise NotRecognized("the layer only references a named style")
    user_style = layer.pick_style(style)
    if user_style is None:
        wanted = f"no user style named {style}" if style else "several user styles, none default"
        raise NotRecognized(wanted)
    notes = layer.unsupported + user_style.unsupported
    if notes:
        raise NotRecognized("unsupported content: " + "; ".join(notes))
    if len(user_style.styles) != 1:
        raise NotRecognized("expected a single FeatureTypeStyle")
    return user_style, user_style.styles[0].rules


def is_text_rule(rule: Rule) -> bool:
    return all(isinstance(item, TextSymbolizer) for item in rule.symbolizers)


def split_text_rules(rules: tuple[Rule, ...]) -> tuple[list[Rule], Rule | None]:
    text_rules = [rule for rule in rules if is_text_rule(rule)]
    if len(text_rules) > 1:
        raise NotRecognized("more than one label rule")
    others = [rule for rule in rules if not is_text_rule(rule)]
    return others, text_rules[0] if text_rules else None


def only(symbolizers: tuple[Symbolizer, ...], kind: type, what: str) -> Symbolizer:
    if len(symbolizers) != 1 or not isinstance(symbolizers[0], kind):
        raise NotRecognized(f"{what} must hold exactly one {kind.__name__}")
    return symbolizers[0]
