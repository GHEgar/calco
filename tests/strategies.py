from __future__ import annotations

from typing import Any

from hypothesis import strategies as st

from calco import (
    Annotation,
    Categories,
    Category,
    Choropleth,
    ExternalGraphic,
    Fill,
    Font,
    Function,
    Graphic,
    Halo,
    Hatch,
    Label,
    Line,
    LinePlacement,
    Literal,
    Mark,
    NullStyle,
    Other,
    Point,
    PointPlacement,
    Polygon,
    Property,
    ScaleRange,
    Stroke,
)
from calco.expressions import Expression

names = st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,15}", fullmatch=True)
texts = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc"), blacklist_characters="￾￿"),
    max_size=20,
).map(str.strip)
optional_texts = st.none() | texts
colors = st.from_regex(r"#[0-9A-F]{6}", fullmatch=True)
unit = st.integers(0, 100).map(lambda value: value / 100)
sizes = st.integers(0, 4000).map(lambda value: value / 100)
numbers = st.integers(-(10**6), 10**6) | st.floats(-1e6, 1e6, allow_nan=False, allow_infinity=False)


@st.composite
def scale_ranges(draw: st.DrawFn) -> ScaleRange:
    low = draw(st.none() | st.integers(1, 10**6))
    high = draw(st.none() | st.integers(10**6 + 1, 10**9))
    return ScaleRange(low, high)


strokes = st.builds(
    Stroke,
    color=colors,
    width=sizes,
    opacity=unit,
    linejoin=st.none() | st.sampled_from(("miter", "round", "bevel")),
    linecap=st.none() | st.sampled_from(("butt", "round", "square")),
    dasharray=st.none() | st.lists(sizes, min_size=1, max_size=4).map(tuple),
)
fills = st.builds(Fill, color=colors, opacity=unit)
hatches = st.builds(
    Hatch,
    mark=st.sampled_from(("shape://times", "shape://slash", "shape://backslash")),
    color=colors,
    size=sizes,
    width=sizes,
    opacity=unit,
)
simple_expressions: st.SearchStrategy[Expression] = st.builds(Property, names) | st.builds(
    Literal, st.text(alphabet="abc xyz-:,", max_size=8)
)
expressions: st.SearchStrategy[Expression] = simple_expressions | st.builds(
    Function, names, st.lists(simple_expressions, max_size=3).map(tuple)
)
geometries = st.none() | expressions
fonts = st.builds(
    Font,
    family=names,
    size=sizes,
    style=st.sampled_from(("normal", "italic", "oblique")),
    weight=st.sampled_from(("normal", "bold")),
)
placements = st.builds(
    PointPlacement,
    anchor_x=unit,
    anchor_y=unit,
    displacement_x=numbers,
    displacement_y=numbers,
    rotation=numbers,
) | st.builds(LinePlacement, numbers)
labels = st.builds(
    Label,
    content=st.lists(expressions, min_size=1, max_size=3).map(tuple),
    font=fonts,
    fill=fills,
    halo=st.none() | st.builds(Halo, sizes, fills),
    placement=placements,
    geometry=geometries,
    vendor_options=st.dictionaries(names, names, max_size=3),
    scales=scale_ranges(),
)
null_styles = st.builds(
    NullStyle,
    title=optional_texts,
    background=st.none() | fills,
    hatch=st.none() | hatches,
    stroke=strokes,
)


@st.composite
def choropleths(draw: st.DrawFn) -> Choropleth:
    count = draw(st.integers(1, 7))
    cuts = sorted(draw(st.sets(numbers, min_size=count + 1, max_size=count + 1)))
    breaks: list[float | None] = list(cuts)
    if draw(st.booleans()):
        breaks[0] = None
    if draw(st.booleans()):
        breaks[-1] = None
    if count == 1 and breaks[0] is None and breaks[-1] is None:
        breaks[0] = cuts[0]
    return Choropleth.from_breaks(
        draw(names),
        draw(names),
        breaks,
        draw(st.lists(colors, min_size=count, max_size=count)),
        draw(st.lists(optional_texts, min_size=count, max_size=count)),
        **draw(swatches()),
    )


@st.composite
def swatches(draw: st.DrawFn) -> dict[str, Any]:
    kind = draw(st.sampled_from(("polygon", "line", "point")))
    return {
        "kind": kind,
        "stroke": draw(st.none() | strokes),
        "fill_opacity": draw(unit),
        "size": draw(sizes),
        "mark": draw(names),
        "null": draw(st.none() | null_styles) if kind == "polygon" else None,
        "label": draw(st.none() | labels),
        "geometry": draw(geometries),
        "scales": draw(scale_ranges()),
        "title": draw(optional_texts),
        "abstract": draw(optional_texts),
        "style_name": draw(st.none() | names),
    }


headers = {
    "title": optional_texts,
    "abstract": optional_texts,
    "style_name": st.none() | names,
    "rule_name": st.none() | names,
    "rule_title": optional_texts,
}


@st.composite
def polygons(draw: st.DrawFn) -> Polygon:
    fill = draw(st.none() | fills | hatches)
    stroke = draw(strokes if fill is None else st.none() | strokes)
    return Polygon(
        draw(names),
        fill,
        stroke,
        draw(st.none() | labels),
        draw(geometries),
        draw(scale_ranges()),
        **{key: draw(value) for key, value in headers.items()},
    )


marks = st.builds(Mark, name=names, fill=st.none() | fills, stroke=st.none() | strokes)
externals = st.builds(
    ExternalGraphic,
    href=st.from_regex(r"https://example\.org/[a-z]{1,8}\.png", fullmatch=True),
    format=st.sampled_from(("image/png", "image/svg+xml")),
)
graphics = st.builds(
    Graphic,
    symbol=marks | externals,
    size=st.none() | sizes,
    rotation=numbers,
    opacity=unit,
    anchor=st.none() | st.tuples(unit, unit),
    displacement=st.none() | st.tuples(numbers, numbers),
)


@st.composite
def points(draw: st.DrawFn) -> Point:
    return Point(
        draw(names),
        draw(graphics),
        draw(st.none() | labels),
        draw(geometries),
        draw(scale_ranges()),
        **{key: draw(value) for key, value in headers.items()},
    )


category_values = st.text(alphabet="abcxyz 0123456789-_", max_size=8) | st.integers(-1000, 1000)


@st.composite
def categories(draw: st.DrawFn) -> Categories:
    values = draw(st.lists(category_values, min_size=1, max_size=9, unique_by=_category_key))
    groups: list[tuple[int | str, ...]] = []
    while values:
        take = draw(st.integers(1, min(3, len(values))))
        groups.append(tuple(values[:take]))
        values = values[take:]
    return Categories(
        draw(names),
        draw(names),
        tuple(Category(group, draw(colors), draw(optional_texts)) for group in groups),
        draw(st.none() | st.builds(Other, colors, optional_texts)),
        **draw(swatches()),
    )


def _category_key(value: int | str) -> float | str:
    return Category(value, "#000000").values[0]


@st.composite
def lines(draw: st.DrawFn) -> Line:
    return Line(
        draw(names),
        tuple(draw(st.lists(strokes, min_size=1, max_size=3))),
        draw(st.none() | labels),
        draw(geometries),
        draw(scale_ranges()),
        **{key: draw(value) for key, value in headers.items()},
    )


annotation_styles = st.builds(
    Annotation,
    layer=names,
    label=labels,
    title=optional_texts,
    abstract=optional_texts,
    style_name=st.none() | names,
)
