from __future__ import annotations

from hypothesis import given, settings

from calco import Choropleth, Point, Polygon, parse, recognize, write
from tests.strategies import choropleths, points, polygons

Recipe = Choropleth | Polygon | Point


def assert_round_trip(recipe: Recipe) -> None:
    xml = write(recipe.to_layer())
    document = parse(xml)
    assert document.all_unsupported == ()
    assert recognize(document) == recipe
    assert write(document) == xml
    assert parse(write(recipe.to_layer(), pretty=False)) == document


@settings(max_examples=300)
@given(choropleths())
def test_choropleth_round_trip(recipe: Choropleth) -> None:
    assert_round_trip(recipe)


@settings(max_examples=200)
@given(polygons())
def test_polygon_round_trip(recipe: Polygon) -> None:
    assert_round_trip(recipe)


@settings(max_examples=200)
@given(points())
def test_point_round_trip(recipe: Point) -> None:
    assert_round_trip(recipe)
