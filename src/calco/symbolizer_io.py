from __future__ import annotations

from xml.etree.ElementTree import Element

from calco.errors import InvalidModel
from calco.expressions import Expression, read_mixed, read_single, write_expression
from calco.graphics_io import (
    PARAMS,
    read_fill,
    read_graphic,
    read_stroke,
    write_fill,
    write_graphic,
    write_stroke,
)
from calco.symbolizers import (
    Fill,
    Font,
    Halo,
    LinePlacement,
    LineSymbolizer,
    PointPlacement,
    PointSymbolizer,
    PolygonSymbolizer,
    Symbolizer,
    TextSymbolizer,
)
from calco.values import format_number
from calco.xmltools import SLD, Children, Reader, local, sub, sub_number, write_params

SYMBOLIZER_TAGS = ("PolygonSymbolizer", "LineSymbolizer", "PointSymbolizer", "TextSymbolizer")
FONT_PARAMS = ("font-family", "font-size", "font-style", "font-weight")


def write_symbolizer(parent: Element, symbolizer: Symbolizer) -> None:
    node = sub(parent, SLD, type(symbolizer).__name__)
    if symbolizer.geometry is not None:
        write_expression(sub(node, SLD, "Geometry"), symbolizer.geometry)
    if isinstance(symbolizer, PolygonSymbolizer):
        if symbolizer.fill is not None:
            write_fill(node, symbolizer.fill)
        if symbolizer.stroke is not None:
            write_stroke(node, symbolizer.stroke)
    elif isinstance(symbolizer, LineSymbolizer):
        write_stroke(node, symbolizer.stroke)
    elif isinstance(symbolizer, PointSymbolizer):
        write_graphic(node, symbolizer.graphic)
    else:
        _write_text(node, symbolizer)


def _write_text(node: Element, text: TextSymbolizer) -> None:
    label = sub(node, SLD, "Label")
    for part in text.parts:
        write_expression(label, part)
    if text.font is not None:
        font = sub(node, SLD, "Font")
        write_params(
            font,
            [
                ("font-family", text.font.family),
                ("font-size", format_number(text.font.size)),
                ("font-style", text.font.style),
                ("font-weight", text.font.weight),
            ],
        )
    if text.placement is not None:
        _write_placement(sub(node, SLD, "LabelPlacement"), text.placement)
    if text.halo is not None:
        halo = sub(node, SLD, "Halo")
        sub_number(halo, "Radius", text.halo.radius)
        write_fill(halo, text.halo.fill)
    if text.fill is not None:
        write_fill(node, text.fill)
    for name, value in text.vendor_options.items():
        sub(node, SLD, "VendorOption", value).set("name", name)


def _write_placement(parent: Element, placement: PointPlacement | LinePlacement) -> None:
    if isinstance(placement, LinePlacement):
        sub_number(sub(parent, SLD, "LinePlacement"), "PerpendicularOffset", placement.offset)
        return
    point = sub(parent, SLD, "PointPlacement")
    anchor = sub(point, SLD, "AnchorPoint")
    sub_number(anchor, "AnchorPointX", placement.anchor_x)
    sub_number(anchor, "AnchorPointY", placement.anchor_y)
    displacement = sub(point, SLD, "Displacement")
    sub_number(displacement, "DisplacementX", placement.displacement_x)
    sub_number(displacement, "DisplacementY", placement.displacement_y)
    sub_number(point, "Rotation", placement.rotation)


def read_symbolizer(reader: Reader, elem: Element, path: str) -> Symbolizer | None:
    name = local(elem.tag)
    allowed = {
        "PolygonSymbolizer": ("Geometry", "Fill", "Stroke"),
        "LineSymbolizer": ("Geometry", "Stroke"),
        "PointSymbolizer": ("Geometry", "Graphic"),
        "TextSymbolizer": (
            "Geometry",
            "Label",
            "Font",
            "LabelPlacement",
            "Halo",
            "Fill",
            "VendorOption",
        ),
    }[name]
    groups = reader.children(elem, path, allowed)
    geometry_node = reader.one(groups, "Geometry")
    geometry = None if geometry_node is None else read_single(reader, *geometry_node)
    if geometry_node is not None and geometry is None:
        return None
    try:
        if name == "PolygonSymbolizer":
            return _read_polygon(reader, groups, geometry)
        if name == "LineSymbolizer":
            stroke_node = reader.one(groups, "Stroke")
            stroke = None if stroke_node is None else read_stroke(reader, *stroke_node)
            if stroke_node is not None and stroke is None:
                return None
            return LineSymbolizer(stroke or LineSymbolizer().stroke, geometry)
        if name == "PointSymbolizer":
            graphic_node = reader.one(groups, "Graphic")
            graphic = None if graphic_node is None else read_graphic(reader, *graphic_node)
            if graphic_node is not None and graphic is None:
                return None
            return PointSymbolizer(graphic or PointSymbolizer().graphic, geometry)
        return _read_text(reader, groups, geometry, path)
    except InvalidModel as exc:
        reader.note(path, str(exc))
        return None


def _read_polygon(
    reader: Reader, groups: Children, geometry: Expression | None
) -> PolygonSymbolizer | None:
    fill_node = reader.one(groups, "Fill")
    stroke_node = reader.one(groups, "Stroke")
    fill = None if fill_node is None else read_fill(reader, *fill_node)
    stroke = None if stroke_node is None else read_stroke(reader, *stroke_node)
    if (fill_node and fill is None) or (stroke_node and stroke is None):
        return None
    return PolygonSymbolizer(fill=fill, stroke=stroke, geometry=geometry)


def _read_text(
    reader: Reader, groups: Children, geometry: Expression | None, path: str
) -> TextSymbolizer | None:
    label_node = reader.one(groups, "Label")
    label = None if label_node is None else read_mixed(reader, *label_node)
    if not label:
        reader.note(path, "TextSymbolizer without a readable Label")
        return None
    fill_node = reader.one(groups, "Fill")
    fill = None if fill_node is None else read_fill(reader, *fill_node)
    if fill_node is not None and not isinstance(fill, Fill):
        reader.note(fill_node[1], "text fill must be a plain color")
        return None
    halo_node = reader.one(groups, "Halo")
    halo = None if halo_node is None else _read_halo(reader, *halo_node)
    if halo_node is not None and halo is None:
        return None
    font_node = reader.one(groups, "Font")
    placement_node = reader.one(groups, "LabelPlacement")
    placement = None if placement_node is None else _read_placement(reader, *placement_node)
    if placement_node is not None and placement is None:
        return None
    options: dict[str, str] = {}
    for option, option_path in groups.get("VendorOption", []):
        option_name = option.get("name", "").strip()
        if option_name and option.text and option.text.strip():
            options[option_name] = option.text.strip()
        else:
            reader.note(option_path, "VendorOption without name or value")
    return TextSymbolizer(
        label=label,
        font=None if font_node is None else _read_font(reader, *font_node),
        placement=placement,
        halo=halo,
        fill=fill if isinstance(fill, Fill) else None,
        geometry=geometry,
        vendor_options=options,
    )


def _read_font(reader: Reader, elem: Element, path: str) -> Font:
    reader.children(elem, path, PARAMS)
    params = reader.params(elem, path, FONT_PARAMS)
    return Font(
        family=params.get("font-family", "sans-serif"),
        size=reader.param_number(params, "font-size", 10, path),
        style=params.get("font-style", "normal"),
        weight=params.get("font-weight", "normal"),
    )


def _read_halo(reader: Reader, elem: Element, path: str) -> Halo | None:
    groups = reader.children(elem, path, ("Radius", "Fill"))
    fill_node = reader.one(groups, "Fill")
    fill = Fill("#FFFFFF") if fill_node is None else read_fill(reader, *fill_node)
    if not isinstance(fill, Fill):
        reader.note(path, "halo fill must be a plain color")
        return None
    return Halo(radius=reader.number(groups, "Radius", 1) or 0, fill=fill)


def _read_placement(
    reader: Reader, elem: Element, path: str
) -> PointPlacement | LinePlacement | None:
    groups = reader.children(elem, path, ("PointPlacement", "LinePlacement"))
    line = reader.one(groups, "LinePlacement")
    if line is not None:
        inner = reader.children(line[0], line[1], ("PerpendicularOffset",))
        return LinePlacement(reader.number(inner, "PerpendicularOffset", 0) or 0)
    point = reader.one(groups, "PointPlacement")
    if point is None:
        reader.note(path, "LabelPlacement without PointPlacement or LinePlacement")
        return None
    inner = reader.children(point[0], point[1], ("AnchorPoint", "Displacement", "Rotation"))
    values: dict[str, float] = {"anchor_x": 0, "anchor_y": 0.5}
    for group, names in (
        ("AnchorPoint", ("AnchorPointX", "AnchorPointY")),
        ("Displacement", ("DisplacementX", "DisplacementY")),
    ):
        node = reader.one(inner, group)
        if node is None:
            continue
        coords = reader.children(node[0], node[1], names)
        prefix = "anchor" if group == "AnchorPoint" else "displacement"
        for axis, coord_name in zip(("x", "y"), names, strict=True):
            fallback = values.get(f"{prefix}_{axis}", 0)
            values[f"{prefix}_{axis}"] = reader.number(coords, coord_name, fallback) or 0
    values["rotation"] = reader.number(inner, "Rotation", 0) or 0
    return PointPlacement(**values)
