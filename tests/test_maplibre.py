from __future__ import annotations

import math

import pytest

from calco import (
    Choropleth,
    Fill,
    Font,
    Function,
    Halo,
    Label,
    LinePlacement,
    Literal,
    PointPlacement,
    Property,
    ScaleRange,
    parse,
    write,
)
from calco.maplibre import (
    SCALE_AT_ZOOM_0,
    label_layers,
    read_label_rules,
    scale_to_zoom,
    strip_text,
    zoom_to_scale,
)

HEAD = (
    '<StyledLayerDescriptor version="1.0.0" xmlns="http://www.opengis.net/sld" '
    'xmlns:ogc="http://www.opengis.net/ogc">'
)


def styled(label: Label) -> Choropleth:
    return Choropleth.from_breaks("mun", "pob", [0, 10, None], ["#000000", "#FFFFFF"], label=label)


def test_zoom_and_scale_are_inverse() -> None:
    assert scale_to_zoom(SCALE_AT_ZOOM_0, tile_size=256) == 0
    assert scale_to_zoom(SCALE_AT_ZOOM_0) == -1
    assert math.isclose(zoom_to_scale(scale_to_zoom(25_000)), 25_000)


def test_translates_a_full_label() -> None:
    label = Label(
        (Literal("Pob: "), Property("pob")),
        font=Font("Open Sans", 12, weight="bold"),
        fill=Fill("#333333", 0.5),
        halo=Halo(2, Fill("#FFFFFF")),
        placement=PointPlacement(0, 1, 6, 12),
        scales=ScaleRange(None, 500_000),
        vendor_options={"autoWrap": "60", "spaceAround": "4", "group": "yes"},
    )
    result = label_layers(parse(write(styled(label).to_layer())), source="mun")
    assert result.skipped == []
    (layer,) = result.layers
    assert layer["id"] == "calco-mun-0"
    assert layer["type"] == "symbol"
    assert layer["source"] == "mun"
    assert math.isclose(layer["minzoom"], scale_to_zoom(500_000), abs_tol=1e-6)
    assert "maxzoom" not in layer
    assert layer["layout"] == {
        "text-field": ["concat", "Pob: ", ["to-string", ["get", "pob"]]],
        "text-font": ["Open Sans Bold"],
        "text-size": 12,
        "text-anchor": "top-left",
        "text-offset": [0.5, -1.0],
        "text-max-width": 5.0,
        "text-padding": 4,
    }
    assert layer["paint"] == {
        "text-color": "rgba(51, 51, 51, 0.5)",
        "text-halo-color": "#FFFFFF",
        "text-halo-width": 2,
    }
    assert any("group" in note for note in result.notes)


def test_line_placement_and_custom_fonts() -> None:
    label = Label(Property("calle"), placement=LinePlacement(5), font=Font("Garet", 10))
    result = label_layers(
        styled(label).to_layer(),
        source="vias",
        source_layer="calles",
        fonts=lambda font: [font.family, "Noto Sans Regular"],
    )
    (layer,) = result.layers
    assert layer["source-layer"] == "calles"
    assert layer["layout"]["symbol-placement"] == "line"
    assert layer["layout"]["text-offset"] == [0, -0.5]
    assert layer["layout"]["text-font"] == ["Garet", "Noto Sans Regular"]


def test_skips_functions_without_equivalent() -> None:
    label = Label(Function("strToUpperCase", (Property("n"),)))
    result = label_layers(styled(label).to_layer(), source="s")
    assert result.layers == []
    assert "strToUpperCase" in result.skipped[0].reason


def test_concatenate_is_flattened() -> None:
    label = Label(Function("Concatenate", (Property("a"), Literal("-"), Property("b"))))
    (layer,) = label_layers(styled(label).to_layer(), source="s").layers
    assert layer["layout"]["text-field"] == [
        "concat",
        ["to-string", ["get", "a"]],
        "-",
        ["to-string", ["get", "b"]],
    ]


def rules_xml(rules: str) -> str:
    return (
        f"{HEAD}<NamedLayer><Name>n</Name><UserStyle><FeatureTypeStyle>{rules}"
        "</FeatureTypeStyle></UserStyle></NamedLayer></StyledLayerDescriptor>"
    )


TEXT = "<TextSymbolizer><Label><ogc:PropertyName>n</ogc:PropertyName></Label></TextSymbolizer>"


def test_filters_and_else_filters() -> None:
    xml = rules_xml(
        "<Rule><ogc:Filter><ogc:PropertyIsGreaterThan><ogc:PropertyName>p</ogc:PropertyName>"
        f"<ogc:Literal>5</ogc:Literal></ogc:PropertyIsGreaterThan></ogc:Filter>{TEXT}</Rule>"
        f"<Rule><ElseFilter/>{TEXT}</Rule>"
    )
    first, second = label_layers(parse(xml), source="s").layers
    assert first["filter"] == [">", ["get", "p"], 5]
    assert second["filter"] == ["!", [">", ["get", "p"], 5]]
    assert first["layout"]["text-anchor"] == "left"


def test_else_filter_that_never_applies_is_skipped() -> None:
    xml = rules_xml(f"<Rule><PolygonSymbolizer/></Rule><Rule><ElseFilter/>{TEXT}</Rule>")
    result = label_layers(parse(xml), source="s")
    assert result.layers == []
    assert "never applies" in result.skipped[0].reason


def test_read_label_rules_counts_every_text_symbolizer() -> None:
    xml = rules_xml(f"<Rule>{TEXT}{TEXT}</Rule><Rule><PolygonSymbolizer/></Rule>")
    assert [rule.index for rule in read_label_rules(parse(xml))] == [0, 1]


def test_strip_text_keeps_everything_else() -> None:
    xml = write(styled(Label(Property("n"), scales=ScaleRange(1, 2))).to_layer())
    stripped = strip_text(xml)
    assert "TextSymbolizer" not in stripped
    assert ">\n" not in stripped
    document = parse(stripped)
    assert len(document.layers[0].rules) == 2
    assert any("rule dropped" in note for note in document.all_unsupported)


def test_strip_text_keeps_literal_whitespace() -> None:
    xml = rules_xml(
        "<Rule><ogc:Filter><ogc:PropertyIsEqualTo><ogc:PropertyName>a</ogc:PropertyName>"
        f"<ogc:Literal> </ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>{TEXT}"
        "<PolygonSymbolizer/></Rule>"
    )
    assert "<ogc:Literal> </ogc:Literal>" in strip_text(xml)


@pytest.mark.parametrize("scale", [0, -1])
def test_scale_must_be_positive(scale: float) -> None:
    with pytest.raises(ValueError, match="positive"):
        scale_to_zoom(scale)


def test_between_filters_translate() -> None:
    xml = rules_xml(
        "<Rule><ogc:Filter><ogc:PropertyIsBetween><ogc:PropertyName>p</ogc:PropertyName>"
        "<ogc:LowerBoundary><ogc:Literal>1</ogc:Literal></ogc:LowerBoundary><ogc:UpperBoundary>"
        f"<ogc:Literal>2</ogc:Literal></ogc:UpperBoundary></ogc:PropertyIsBetween></ogc:Filter>{TEXT}"
        "</Rule>"
    )
    (layer,) = label_layers(parse(xml), source="s").layers
    assert layer["filter"] == ["all", [">=", ["get", "p"], 1], ["<=", ["get", "p"], 2]]


def test_ambiguous_user_styles_are_reported() -> None:
    style = f"<UserStyle><FeatureTypeStyle><Rule>{TEXT}</Rule></FeatureTypeStyle></UserStyle>"
    xml = f"{HEAD}<NamedLayer><Name>n</Name>{style}{style}</NamedLayer></StyledLayerDescriptor>"
    result = label_layers(parse(xml), source="s")
    assert result.layers == []
    assert "none default" in result.skipped[0].reason
