from __future__ import annotations

from dataclasses import dataclass, field

from calco.errors import NotRecognized
from calco.model import StyledLayer, StyledLayerDescriptor
from calco.recipes import Choropleth, Point, Polygon

Recipe = Choropleth | Polygon | Point
RECIPES: tuple[type[Choropleth] | type[Polygon] | type[Point], ...] = (Choropleth, Polygon, Point)


@dataclass(frozen=True)
class Unrecognized:
    reasons: dict[str, str] = field(default_factory=dict)


def recognize(
    source: StyledLayerDescriptor | StyledLayer, style: str | None = None
) -> Recipe | Unrecognized:
    if isinstance(source, StyledLayerDescriptor):
        if source.unsupported:
            return Unrecognized({"document": "unsupported: " + "; ".join(source.unsupported)})
        if len(source.layers) != 1:
            return Unrecognized({"document": "recipes describe a single layer"})
        source = source.layers[0]
    reasons: dict[str, str] = {}
    for recipe in RECIPES:
        try:
            return recipe.from_layer(source, style)
        except NotRecognized as exc:
            reasons[recipe.__name__] = str(exc)
    return Unrecognized(reasons)
