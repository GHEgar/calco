from __future__ import annotations

from dataclasses import dataclass, field

from calco.errors import InvalidModel
from calco.expressions import Expression, as_expressions, optional_expression
from calco.values import (
    choice,
    in_range,
    non_negative,
    optional_number,
    required_text,
    set_field,
    to_color,
    to_number,
)

LINEJOINS = ("miter", "mitre", "round", "bevel")
LINECAPS = ("butt", "round", "square")
FONT_STYLES = ("normal", "italic", "oblique")
FONT_WEIGHTS = ("normal", "bold")


def _pair(value: object, field_name: str) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, tuple | list) or len(value) != 2:
        raise InvalidModel(f"{field_name} must be an (x, y) pair")
    return (to_number(value[0], field_name), to_number(value[1], field_name))


def _optional(value: object, kind: type | tuple[type, ...], field_name: str) -> None:
    if value is not None and not isinstance(value, kind):
        raise InvalidModel(f"{field_name} has the wrong type: {value!r}")


@dataclass(frozen=True)
class Stroke:
    color: str = "#000000"
    width: float = 1
    opacity: float = 1
    linejoin: str | None = None
    linecap: str | None = None
    dasharray: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        set_field(self, "color", to_color(self.color, "Stroke.color"))
        set_field(self, "width", non_negative(self.width, "Stroke.width"))
        set_field(self, "opacity", in_range(self.opacity, "Stroke.opacity", 0, 1))
        if self.linejoin is not None:
            choice(self.linejoin, "Stroke.linejoin", LINEJOINS)
        if self.linecap is not None:
            choice(self.linecap, "Stroke.linecap", LINECAPS)
        if self.dasharray is not None:
            dashes = tuple(non_negative(item, "Stroke.dasharray") for item in self.dasharray)
            if not dashes:
                raise InvalidModel("Stroke.dasharray must not be empty")
            set_field(self, "dasharray", dashes)


@dataclass(frozen=True)
class Fill:
    color: str = "#808080"
    opacity: float = 1

    def __post_init__(self) -> None:
        set_field(self, "color", to_color(self.color, "Fill.color"))
        set_field(self, "opacity", in_range(self.opacity, "Fill.opacity", 0, 1))


@dataclass(frozen=True)
class Mark:
    name: str = "square"
    fill: Fill | None = Fill()
    stroke: Stroke | None = Stroke()

    def __post_init__(self) -> None:
        set_field(self, "name", required_text(self.name, "Mark.name"))
        _optional(self.fill, Fill, "Mark.fill")
        _optional(self.stroke, Stroke, "Mark.stroke")


@dataclass(frozen=True)
class ExternalGraphic:
    href: str
    format: str = "image/png"

    def __post_init__(self) -> None:
        set_field(self, "href", required_text(self.href, "ExternalGraphic.href"))
        set_field(self, "format", required_text(self.format, "ExternalGraphic.format"))


@dataclass(frozen=True)
class Graphic:
    symbol: Mark | ExternalGraphic = Mark()
    size: float | None = None
    rotation: float = 0
    opacity: float = 1
    anchor: tuple[float, float] | None = None
    displacement: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        for name in ("anchor", "displacement"):
            set_field(self, name, _pair(getattr(self, name), f"Graphic.{name}"))
        if not isinstance(self.symbol, Mark | ExternalGraphic):
            raise InvalidModel("Graphic.symbol must be a Mark or an ExternalGraphic")
        size = optional_number(self.size, "Graphic.size")
        if size is not None:
            non_negative(size, "Graphic.size")
        set_field(self, "size", size)
        set_field(self, "rotation", to_number(self.rotation, "Graphic.rotation"))
        set_field(self, "opacity", in_range(self.opacity, "Graphic.opacity", 0, 1))


@dataclass(frozen=True)
class GraphicFill:
    graphic: Graphic

    def __post_init__(self) -> None:
        if not isinstance(self.graphic, Graphic):
            raise InvalidModel("GraphicFill.graphic must be a Graphic")


@dataclass(frozen=True)
class PolygonSymbolizer:
    fill: Fill | GraphicFill | None = Fill()
    stroke: Stroke | None = Stroke()
    geometry: Expression | None = None

    def __post_init__(self) -> None:
        _optional(self.fill, (Fill, GraphicFill), "PolygonSymbolizer.fill")
        _optional(self.stroke, Stroke, "PolygonSymbolizer.stroke")
        optional_expression(self.geometry, "PolygonSymbolizer.geometry")


@dataclass(frozen=True)
class LineSymbolizer:
    stroke: Stroke = Stroke()
    geometry: Expression | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.stroke, Stroke):
            raise InvalidModel("LineSymbolizer.stroke must be a Stroke")
        optional_expression(self.geometry, "LineSymbolizer.geometry")


@dataclass(frozen=True)
class PointSymbolizer:
    graphic: Graphic = Graphic()
    geometry: Expression | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.graphic, Graphic):
            raise InvalidModel("PointSymbolizer.graphic must be a Graphic")
        optional_expression(self.geometry, "PointSymbolizer.geometry")


@dataclass(frozen=True)
class Font:
    family: str = "sans-serif"
    size: float = 10
    style: str = "normal"
    weight: str = "normal"

    def __post_init__(self) -> None:
        set_field(self, "family", required_text(self.family, "Font.family"))
        set_field(self, "size", non_negative(self.size, "Font.size"))
        style = self.style.lower() if isinstance(self.style, str) else self.style
        weight = self.weight.lower() if isinstance(self.weight, str) else self.weight
        set_field(self, "style", choice(style, "Font.style", FONT_STYLES))
        set_field(self, "weight", choice(weight, "Font.weight", FONT_WEIGHTS))


@dataclass(frozen=True)
class Halo:
    radius: float = 1
    fill: Fill = Fill("#FFFFFF")

    def __post_init__(self) -> None:
        set_field(self, "radius", non_negative(self.radius, "Halo.radius"))
        if not isinstance(self.fill, Fill):
            raise InvalidModel("Halo.fill must be a Fill")


@dataclass(frozen=True)
class PointPlacement:
    anchor_x: float = 0.5
    anchor_y: float = 0.5
    displacement_x: float = 0
    displacement_y: float = 0
    rotation: float = 0

    def __post_init__(self) -> None:
        for name in ("anchor_x", "anchor_y", "displacement_x", "displacement_y", "rotation"):
            set_field(self, name, to_number(getattr(self, name), f"PointPlacement.{name}"))


@dataclass(frozen=True)
class LinePlacement:
    offset: float = 0

    def __post_init__(self) -> None:
        set_field(self, "offset", to_number(self.offset, "LinePlacement.offset"))


@dataclass(frozen=True)
class TextSymbolizer:
    label: tuple[Expression, ...] | Expression
    font: Font | None = Font()
    placement: PointPlacement | LinePlacement | None = None
    halo: Halo | None = None
    fill: Fill | None = Fill("#000000")
    geometry: Expression | None = None
    vendor_options: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        set_field(self, "label", as_expressions(self.label, "TextSymbolizer.label"))
        _optional(self.font, Font, "TextSymbolizer.font")
        _optional(self.placement, (PointPlacement, LinePlacement), "TextSymbolizer.placement")
        _optional(self.halo, Halo, "TextSymbolizer.halo")
        _optional(self.fill, Fill, "TextSymbolizer.fill")
        optional_expression(self.geometry, "TextSymbolizer.geometry")
        set_field(self, "vendor_options", vendor_options(self.vendor_options))

    @property
    def parts(self) -> tuple[Expression, ...]:
        return as_expressions(self.label, "TextSymbolizer.label")


def vendor_options(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise InvalidModel("vendor_options must be a dict of strings")
    return {
        required_text(key, "vendor option name"): required_text(item, f"vendor option {key}")
        for key, item in value.items()
    }


Symbolizer = PolygonSymbolizer | LineSymbolizer | PointSymbolizer | TextSymbolizer
