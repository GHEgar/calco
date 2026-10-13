from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from lxml import etree

from calco import Choropleth, Label, Point, Polygon, Property, write
from tests.strategies import choropleths, points, polygons

SCHEMA = etree.XMLSchema(
    etree.parse(Path(__file__).parent / "fixtures/schemas/sld/1.0.0/StyledLayerDescriptor.xsd")
)


def plain(recipe: Choropleth | Polygon | Point) -> bool:
    labels = [recipe.label] if recipe.label is not None else []
    if recipe.geometry is not None and not isinstance(recipe.geometry, Property):
        return False
    return all(
        not label.vendor_options and isinstance(label.geometry, Property | None) for label in labels
    )


def assert_valid(recipe: Choropleth | Polygon | Point) -> None:
    document = etree.fromstring(write(recipe.to_layer()).encode())
    assert SCHEMA.validate(document), SCHEMA.error_log


@settings(max_examples=100)
@given(choropleths())
def test_choropleths_validate(recipe: Choropleth) -> None:
    if plain(recipe):
        assert_valid(recipe)


@settings(max_examples=100)
@given(polygons())
def test_polygons_validate(recipe: Polygon) -> None:
    if plain(recipe):
        assert_valid(recipe)


@settings(max_examples=100)
@given(points())
def test_points_validate(recipe: Point) -> None:
    if plain(recipe):
        assert_valid(recipe)


def test_geoserver_extensions_do_not_validate() -> None:
    recipe = Polygon("l", label=Label(Property("n"), vendor_options={"autoWrap": "80"}))
    document = etree.fromstring(write(recipe.to_layer()).encode())
    assert not SCHEMA.validate(document)
