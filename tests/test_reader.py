from __future__ import annotations

import pytest

from calco import (
    And,
    Annotation,
    Between,
    Choropleth,
    Compare,
    Fill,
    IsNull,
    Label,
    Literal,
    ParseError,
    Polygon,
    PolygonSymbolizer,
    Property,
    ScaleRange,
    Stroke,
    TextSymbolizer,
    Unrecognized,
    parse,
    recognize,
    write,
)

HEAD = (
    '<StyledLayerDescriptor version="1.0.0" xmlns="http://www.opengis.net/sld" '
    'xmlns:ogc="http://www.opengis.net/ogc" xmlns:xlink="http://www.w3.org/1999/xlink">'
)


def sld(rules: str, extra: str = "") -> str:
    return (
        f"{HEAD}<NamedLayer><Name>capa</Name><UserStyle><Title>Estilo</Title>"
        f"<FeatureTypeStyle>{rules}</FeatureTypeStyle>{extra}</UserStyle></NamedLayer>"
        "</StyledLayerDescriptor>"
    )


def range_rule(lower: str | None, upper: str | None, color: str, upper_tag: str = "") -> str:
    parts = []
    if lower is not None:
        parts.append(
            "<ogc:PropertyIsGreaterThanOrEqualTo><ogc:PropertyName>pob</ogc:PropertyName>"
            f"<ogc:Literal>{lower}</ogc:Literal></ogc:PropertyIsGreaterThanOrEqualTo>"
        )
    if upper is not None:
        tag = upper_tag or "PropertyIsLessThan"
        parts.append(
            f"<ogc:{tag}><ogc:PropertyName>pob</ogc:PropertyName>"
            f"<ogc:Literal>{upper}</ogc:Literal></ogc:{tag}>"
        )
    body = parts[0] if len(parts) == 1 else f"<ogc:And>{''.join(parts)}</ogc:And>"
    return (
        f"<Rule><Title>{lower}-{upper}</Title><ogc:Filter>{body}</ogc:Filter>"
        f'<PolygonSymbolizer><Fill><SvgParameter name="fill">{color}</SvgParameter></Fill>'
        '<Stroke><CssParameter name="stroke">#ffffff</CssParameter>'
        '<CssParameter name="stroke-width">0.5</CssParameter></Stroke></PolygonSymbolizer></Rule>'
    )


def test_reads_a_foreign_choropleth_with_svg_parameters() -> None:
    xml = sld(
        range_rule("0", "10", "#fee5d9")
        + range_rule("10", "20.5", "#fcae91")
        + range_rule("20.5", "100", "#cb181d", "PropertyIsLessThanOrEqualTo")
    )
    recipe = recognize(parse(xml))
    assert isinstance(recipe, Choropleth)
    assert recipe.breaks == (0, 10, 20.5, 100)
    assert recipe.classes[0].color == "#FEE5D9"
    assert recipe.stroke == Stroke("#FFFFFF", 0.5)
    assert recipe.title == "Estilo"


def test_rejects_gaps_between_ranges() -> None:
    xml = sld(range_rule("0", "10", "#fee5d9") + range_rule("12", None, "#cb181d"))
    result = recognize(parse(xml))
    assert isinstance(result, Unrecognized)
    assert "does not start where" in result.reasons["Choropleth"]


def test_rejects_a_closed_upper_bound_before_the_last_class() -> None:
    xml = sld(
        range_rule("0", "10", "#fee5d9", "PropertyIsLessThanOrEqualTo")
        + range_rule("10", None, "#cb181d")
    )
    result = recognize(parse(xml))
    assert isinstance(result, Unrecognized)
    assert "<=" in result.reasons["Choropleth"]


def test_records_unsupported_content_with_its_path() -> None:
    xml = sld(
        '<Rule><PolygonSymbolizer><Fill><CssParameter name="fill">'
        "<ogc:PropertyName>color</ogc:PropertyName></CssParameter></Fill></PolygonSymbolizer>"
        "<LegendGraphic/></Rule>",
        "<Transformation/>",
    )
    document = parse(xml)
    notes = document.all_unsupported
    assert any("Rule/LegendGraphic" in note for note in notes)
    assert any("CssParameter[@name='fill']" in note for note in notes)
    assert any("UserStyle/Transformation" in note for note in notes)
    result = recognize(document)
    assert isinstance(result, Unrecognized)
    assert all("unsupported content" in reason for reason in result.reasons.values())


def test_reads_mixed_label_content_and_vendor_options() -> None:
    xml = sld(
        "<Rule><TextSymbolizer><Label>Pob: <ogc:PropertyName>pob</ogc:PropertyName>"
        '<ogc:Function name="strToUpperCase"><ogc:PropertyName>nom</ogc:PropertyName>'
        '</ogc:Function></Label><VendorOption name="autoWrap">80</VendorOption>'
        "</TextSymbolizer></Rule>"
    )
    rule = parse(xml).layers[0].rules[0]
    text = rule.symbolizers[0]
    assert isinstance(text, TextSymbolizer)
    assert text.parts[0] == Literal("Pob: ")
    assert text.parts[1] == Property("pob")
    assert text.vendor_options == {"autoWrap": "80"}
    assert text.font is None


def test_reads_null_and_else_filters() -> None:
    xml = sld(
        "<Rule><ogc:Filter><ogc:PropertyIsNull><ogc:PropertyName>pob</ogc:PropertyName>"
        "</ogc:PropertyIsNull></ogc:Filter><PolygonSymbolizer/></Rule>"
        "<Rule><ElseFilter/><PolygonSymbolizer/></Rule>"
    )
    first, second = parse(xml).layers[0].rules
    assert first.filter == IsNull("pob")
    assert second.else_filter
    assert first.symbolizers == (PolygonSymbolizer(None, None),)


def test_keeps_string_comparisons() -> None:
    xml = sld(
        "<Rule><ogc:Filter><ogc:And><ogc:PropertyIsEqualTo><ogc:PropertyName>tipo</ogc:PropertyName>"
        "<ogc:Literal>urbano</ogc:Literal></ogc:PropertyIsEqualTo><ogc:PropertyIsGreaterThan>"
        "<ogc:PropertyName>pob</ogc:PropertyName><ogc:Literal>1e3</ogc:Literal>"
        "</ogc:PropertyIsGreaterThan></ogc:And></ogc:Filter><PolygonSymbolizer/></Rule>"
    )
    rule = parse(xml).layers[0].rules[0]
    assert rule.filter == And((Compare("tipo", "=", "urbano"), Compare("pob", ">", "1e3")))
    assert Compare("cve", "=", "001").value == "001"
    assert Compare("cve", "=", "15").value == 15


def test_reads_named_styles() -> None:
    xml = (
        f"{HEAD}<NamedLayer><Name>a</Name><NamedStyle><Name>b</Name></NamedStyle></NamedLayer>"
        "</StyledLayerDescriptor>"
    )
    document = parse(xml)
    assert document.layers[0].named_style == "b"
    assert parse(write(document)) == document


def test_a_label_only_style_is_an_annotation() -> None:
    xml = sld(
        "<Rule><TextSymbolizer><Label><ogc:PropertyName>n</ogc:PropertyName></Label>"
        "</TextSymbolizer></Rule>"
    )
    result = recognize(parse(xml))
    assert isinstance(result, Annotation)
    assert result.label.content == (Property("n"),)
    assert result.title == "Estilo"


def test_a_polygon_with_plain_fill() -> None:
    xml = sld(
        '<Rule><PolygonSymbolizer><Fill><CssParameter name="fill">#ABCDEF</CssParameter>'
        "</Fill></PolygonSymbolizer></Rule>"
    )
    assert recognize(parse(xml)) == Polygon("capa", Fill("#ABCDEF"), None, title="Estilo")


@pytest.mark.parametrize(
    "xml",
    ["<nope", "<root/>", f"{HEAD}</StyledLayerDescriptor>"],
)
def test_parse_errors(xml: str) -> None:
    with pytest.raises(ParseError):
        parse(xml)


def test_reads_every_user_style_and_picks_the_default() -> None:
    other = (
        "<UserStyle><Name>otro</Name><FeatureTypeStyle><Rule><ogc:Filter><ogc:PropertyIsBetween>"
        "<ogc:PropertyName>pob</ogc:PropertyName><ogc:LowerBoundary><ogc:Literal>1</ogc:Literal>"
        "</ogc:LowerBoundary><ogc:UpperBoundary><ogc:Literal>2</ogc:Literal></ogc:UpperBoundary>"
        "</ogc:PropertyIsBetween></ogc:Filter><PolygonSymbolizer><Fill>"
        '<CssParameter name="fill">0xAAAAAA</CssParameter></Fill></PolygonSymbolizer>'
        "<LegendGraphic/></Rule></FeatureTypeStyle></UserStyle>"
    )
    xml = (
        f"{HEAD}<NamedLayer><Name>capa</Name>{other}<UserStyle><Name>bueno</Name>"
        "<IsDefault>1</IsDefault><FeatureTypeStyle><Name>name</Name><Rule><PolygonSymbolizer>"
        '<Fill><CssParameter name="fill">#ABCDEF</CssParameter></Fill></PolygonSymbolizer></Rule>'
        "</FeatureTypeStyle></UserStyle></NamedLayer></StyledLayerDescriptor>"
    )
    document = parse(xml)
    layer = document.layers[0]
    assert [style.name for style in layer.user_styles] == ["otro", "bueno"]
    first = layer.user_styles[0].rules[0]
    assert first.filter == Between("pob", 1, 2)
    assert first.symbolizers == (PolygonSymbolizer(Fill("#AAAAAA"), None),)
    expected = Polygon("capa", Fill("#ABCDEF"), None, style_name="bueno")
    assert recognize(document) == expected
    assert isinstance(recognize(document, "otro"), Unrecognized)
    assert parse(write(document)) == document


def test_label_indentation_reads_like_geotools() -> None:
    xml = sld(
        "<Rule><TextSymbolizer><Label>\n  <ogc:PropertyName>a</ogc:PropertyName><![CDATA[ - ]]>\n"
        "  <ogc:PropertyName>b</ogc:PropertyName>\n</Label></TextSymbolizer></Rule>"
    )
    text = parse(xml).layers[0].rules[0].symbolizers[0]
    assert isinstance(text, TextSymbolizer)
    assert text.parts == (Property("a"), Literal(" -  "), Property("b"))


def test_labels_are_written_without_indentation() -> None:
    recipe = Polygon("l", label=Label((Property("a"), Literal(" - "), Property("b"))))
    xml = write(recipe.to_layer())
    assert (
        "<sld:Label><ogc:PropertyName>a</ogc:PropertyName><ogc:Literal> - </ogc:Literal>"
        "<ogc:PropertyName>b</ogc:PropertyName></sld:Label>"
    ) in xml
    assert recognize(parse(xml)) == recipe


SE_SLD = """<StyledLayerDescriptor version="1.1.0" xmlns="http://www.opengis.net/sld"
  xmlns:se="http://www.opengis.net/se" xmlns:ogc="http://www.opengis.net/ogc"
  xmlns:xlink="http://www.w3.org/1999/xlink">
  <NamedLayer><se:Name>capa</se:Name>
    <UserStyle><se:Name>estilo</se:Name>
      <se:Description><se:Title>Título</se:Title><se:Abstract>Resumen</se:Abstract></se:Description>
      <se:FeatureTypeStyle><se:Rule><se:Name>r</se:Name>
        <se:Description><se:Title>Regla</se:Title></se:Description>
        <se:MaxScaleDenominator>100000</se:MaxScaleDenominator>
        <se:PolygonSymbolizer>
          <se:Fill><se:SvgParameter name="fill">#ff0000</se:SvgParameter></se:Fill>
          <se:Stroke><se:SvgParameter name="stroke">#000000</se:SvgParameter>
            <se:SvgParameter name="stroke-width">2</se:SvgParameter></se:Stroke>
        </se:PolygonSymbolizer>
      </se:Rule></se:FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>"""


def test_reads_symbology_encoding_1_1() -> None:
    document = parse(SE_SLD)
    assert document.all_unsupported == ()
    assert recognize(document) == Polygon(
        "capa",
        Fill("#FF0000"),
        Stroke("#000000", 2),
        scales=ScaleRange(None, 100000),
        title="Título",
        abstract="Resumen",
        style_name="estilo",
        rule_name="r",
        rule_title="Regla",
    )
