from __future__ import annotations

from xml.etree.ElementTree import Element

from calco.errors import InvalidModel
from calco.symbolizers import ExternalGraphic, Fill, Graphic, GraphicFill, Mark, Stroke
from calco.values import format_number, parse_number
from calco.xmltools import SLD, XLINK, Reader, local, sub, sub_number, write_params

PARAMS = ("CssParameter", "SvgParameter")
STROKE_PARAMS = (
    "stroke",
    "stroke-width",
    "stroke-opacity",
    "stroke-linejoin",
    "stroke-linecap",
    "stroke-dasharray",
)
FILL_PARAMS = ("fill", "fill-opacity")


def write_stroke(parent: Element, stroke: Stroke) -> None:
    node = sub(parent, SLD, "Stroke")
    dashes = None if stroke.dasharray is None else " ".join(map(format_number, stroke.dasharray))
    write_params(
        node,
        [
            ("stroke", stroke.color),
            ("stroke-width", format_number(stroke.width)),
            ("stroke-opacity", format_number(stroke.opacity)),
            ("stroke-linejoin", stroke.linejoin),
            ("stroke-linecap", stroke.linecap),
            ("stroke-dasharray", dashes),
        ],
    )


def write_fill(parent: Element, fill: Fill | GraphicFill) -> None:
    node = sub(parent, SLD, "Fill")
    if isinstance(fill, GraphicFill):
        write_graphic(sub(node, SLD, "GraphicFill"), fill.graphic)
        return
    write_params(node, [("fill", fill.color), ("fill-opacity", format_number(fill.opacity))])


def write_graphic(parent: Element, graphic: Graphic) -> None:
    node = sub(parent, SLD, "Graphic")
    symbol = graphic.symbol
    if isinstance(symbol, ExternalGraphic):
        external = sub(node, SLD, "ExternalGraphic")
        resource = sub(external, SLD, "OnlineResource")
        resource.set(f"{{{XLINK}}}type", "simple")
        resource.set(f"{{{XLINK}}}href", symbol.href)
        sub(external, SLD, "Format", symbol.format)
    else:
        mark = sub(node, SLD, "Mark")
        sub(mark, SLD, "WellKnownName", symbol.name)
        if symbol.fill is not None:
            write_fill(mark, symbol.fill)
        if symbol.stroke is not None:
            write_stroke(mark, symbol.stroke)
    sub_number(node, "Opacity", graphic.opacity)
    if graphic.size is not None:
        sub_number(node, "Size", graphic.size)
    sub_number(node, "Rotation", graphic.rotation)


def read_stroke(reader: Reader, elem: Element, path: str) -> Stroke | None:
    reader.children(elem, path, PARAMS)
    params = reader.params(elem, path, STROKE_PARAMS)
    dashes: tuple[float, ...] | None = None
    if "stroke-dasharray" in params:
        values = [
            parse_number(item) for item in params["stroke-dasharray"].replace(",", " ").split()
        ]
        if values and all(value is not None for value in values):
            dashes = tuple(value for value in values if value is not None)
        else:
            reader.note(path, "stroke-dasharray is not a list of numbers")
    try:
        return Stroke(
            color=params.get("stroke", "#000000"),
            width=reader.param_number(params, "stroke-width", 1, path),
            opacity=reader.param_number(params, "stroke-opacity", 1, path),
            linejoin=params.get("stroke-linejoin"),
            linecap=params.get("stroke-linecap"),
            dasharray=dashes,
        )
    except InvalidModel as exc:
        reader.note(path, str(exc))
        return None


def read_fill(reader: Reader, elem: Element, path: str) -> Fill | GraphicFill | None:
    groups = reader.children(elem, path, (*PARAMS, "GraphicFill"))
    graphic_fill = reader.one(groups, "GraphicFill")
    if graphic_fill is not None:
        if any(local(child.tag) in PARAMS for child in elem):
            reader.note(path, "parameters next to GraphicFill are not supported")
        graphic_elem, graphic_path = graphic_fill
        inner = reader.children(graphic_elem, graphic_path, ("Graphic",))
        found = reader.one(inner, "Graphic")
        if found is None:
            reader.note(graphic_path, "GraphicFill without Graphic")
            return None
        graphic = read_graphic(reader, *found)
        return None if graphic is None else GraphicFill(graphic)
    params = reader.params(elem, path, FILL_PARAMS)
    try:
        return Fill(
            color=params.get("fill", "#808080"),
            opacity=reader.param_number(params, "fill-opacity", 1, path),
        )
    except InvalidModel as exc:
        reader.note(path, str(exc))
        return None


def read_graphic(reader: Reader, elem: Element, path: str) -> Graphic | None:
    groups = reader.children(elem, path, ("ExternalGraphic", "Mark", "Opacity", "Size", "Rotation"))
    order = list(elem)
    symbols = sorted(
        groups.get("ExternalGraphic", []) + groups.get("Mark", []),
        key=lambda item: order.index(item[0]),
    )
    for _, extra_path in symbols[1:]:
        reader.note(extra_path, "only the first graphic symbol is kept")
    symbol: Mark | ExternalGraphic | None = Mark()
    if symbols:
        symbol_elem, symbol_path = symbols[0]
        if local(symbol_elem.tag) == "Mark":
            symbol = _read_mark(reader, symbol_elem, symbol_path)
        else:
            symbol = _read_external(reader, symbol_elem, symbol_path)
    if symbol is None:
        return None
    try:
        return Graphic(
            symbol=symbol,
            size=reader.number(groups, "Size", None),
            rotation=reader.number(groups, "Rotation", 0) or 0,
            opacity=reader.number(groups, "Opacity", 1) or 0,
        )
    except InvalidModel as exc:
        reader.note(path, str(exc))
        return None


def _read_mark(reader: Reader, elem: Element, path: str) -> Mark | None:
    groups = reader.children(elem, path, ("WellKnownName", "Fill", "Stroke"))
    fill_node = reader.one(groups, "Fill")
    stroke_node = reader.one(groups, "Stroke")
    fill = None if fill_node is None else read_fill(reader, *fill_node)
    stroke = None if stroke_node is None else read_stroke(reader, *stroke_node)
    if (fill_node and fill is None) or (stroke_node and stroke is None):
        return None
    if isinstance(fill, GraphicFill):
        reader.note(path, "a GraphicFill inside a Mark is not supported")
        return None
    try:
        return Mark(name=reader.text(groups, "WellKnownName") or "square", fill=fill, stroke=stroke)
    except InvalidModel as exc:
        reader.note(path, str(exc))
        return None


def _read_external(reader: Reader, elem: Element, path: str) -> ExternalGraphic | None:
    groups = reader.children(elem, path, ("OnlineResource", "Format"))
    resource = reader.one(groups, "OnlineResource")
    href = None if resource is None else resource[0].get(f"{{{XLINK}}}href")
    if not href:
        reader.note(path, "ExternalGraphic without OnlineResource href")
        return None
    try:
        return ExternalGraphic(href=href, format=reader.text(groups, "Format") or "image/png")
    except InvalidModel as exc:
        reader.note(path, str(exc))
        return None
