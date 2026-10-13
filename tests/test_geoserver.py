from __future__ import annotations

import base64
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace

import pytest

from calco import (
    Annotation,
    Categories,
    Choropleth,
    Fill,
    Font,
    Function,
    Graphic,
    Halo,
    Hatch,
    Label,
    Line,
    Literal,
    Mark,
    NullStyle,
    Other,
    Point,
    Polygon,
    Property,
    ScaleRange,
    Stroke,
    Unrecognized,
    parse,
    recognize,
    write,
)
from calco.maplibre import strip_text
from calco.recognize import Recipe

URL = os.environ.get("CALCO_GEOSERVER_URL", "")
AUTH = os.environ.get("CALCO_GEOSERVER_AUTH", "admin:geoserver")

pytestmark = [
    pytest.mark.geoserver,
    pytest.mark.skipif(not URL, reason="set CALCO_GEOSERVER_URL to run against GeoServer"),
]

STATES = ("topp:states", "-125,24,-66,50")
ROADS = ("tiger:tiger_roads", "-74.0118,40.7046,-74.0081,40.7112")
POI = ("tiger:poi", "-74.0118,40.7046,-74.0081,40.7112")
LABEL = Label(Property("STATE_NAME"), font=Font("DejaVu Sans", 11, weight="bold"), halo=Halo(2))
GEOMETRY = Function("property", (Function("env", (Literal("geom"), Literal("the_geom"))),))

CASES: dict[str, tuple[tuple[str, str], Recipe]] = {
    "choropleth": (
        STATES,
        Choropleth.from_breaks(
            "topp:states",
            "PERSONS",
            [None, 2_000_000, 5_000_000, None],
            ["#FEE5D9", "#FCAE91", "#CB181D"],
            ["< 2M", "2M-5M", "> 5M"],
            null=NullStyle(title="Sin dato"),
            geometry=GEOMETRY,
            label=replace(LABEL, scales=ScaleRange(max=50_000_000)),
        ),
    ),
    "categories": (
        STATES,
        Categories.from_values(
            "topp:states",
            "SUB_REGION",
            ["Pacific", "Mountain", "New Eng"],
            ["#1B9E77", "#D95F02", "#7570B3"],
            other=Other("#DDDDDD", "Otras"),
        ),
    ),
    "hatch": (
        STATES,
        Polygon("topp:states", Hatch("shape://slash", "#1F77B4", 8), Stroke("#333333", 0.8)),
    ),
    "line": (ROADS, Line("tiger:tiger_roads", (Stroke("#333333", 5), Stroke("#FFD966", 3)))),
    "point": (
        POI,
        Point(
            "tiger:poi",
            Graphic(Mark("circle", Fill("#D62728"), Stroke("#FFFFFF", 1)), size=10),
            label=Label(Property("NAME"), halo=Halo(1.5)),
        ),
    ),
    "annotation": (STATES, Annotation("topp:states", LABEL)),
    "categories_points": (
        POI,
        Categories.from_values(
            "tiger:poi",
            "NAME",
            [("museam", "art"), "lox"],
            ["#E7298A", "#66A61E"],
            other=Other("#999999"),
            kind="point",
            size=9,
            mark="square",
            stroke=Stroke("#FFFFFF", 1),
        ),
    ),
    "categories_lines": (
        ROADS,
        Categories.from_values(
            "tiger:tiger_roads",
            "CFCC",
            ["A41", ("A45", "A31")],
            ["#555555", "#E6550D"],
            kind="line",
            size=3,
        ),
    ),
    "choropleth_points": (
        STATES,
        Choropleth.from_breaks(
            "topp:states",
            "LAND_KM",
            [None, 100_000, None],
            ["#9ECAE1", "#08519C"],
            kind="point",
            size=12,
        ),
    ),
}


def request(
    method: str, path: str, body: bytes | None = None, kind: str | None = None
) -> tuple[int, str, bytes]:
    headers = {"Authorization": "Basic " + base64.b64encode(AUTH.encode()).decode()}
    if kind:
        headers["Content-Type"] = kind
    message = urllib.request.Request(f"{URL}{path}", body, headers, method=method)
    try:
        with urllib.request.urlopen(message) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type", ""), error.read()


def get_map(layer: str, bbox: str, **params: str) -> tuple[int, str, bytes]:
    query = {
        "service": "WMS",
        "version": "1.1.1",
        "request": "GetMap",
        "layers": layer,
        "bbox": bbox,
        "width": "512",
        "height": "256",
        "srs": "EPSG:4326",
        "format": "image/png",
        **params,
    }
    return request("GET", "/wms?" + urllib.parse.urlencode(query))


@pytest.mark.parametrize("case", sorted(CASES))
def test_geoserver_draws_and_returns_the_recipe(case: str) -> None:
    (layer, bbox), recipe = CASES[case]
    name = f"calco_test_{case}"
    request("DELETE", f"/rest/styles/{name}?purge=true")
    status, _, body = request(
        "POST",
        f"/rest/styles?name={name}",
        write(recipe.to_layer()).encode(),
        "application/vnd.ogc.sld+xml",
    )
    assert status == 201, body
    try:
        status, kind, image = get_map(layer, bbox, styles=name)
        assert (status, kind) == (200, "image/png"), image[:500]
        _, _, stored = request("GET", f"/rest/styles/{name}.sld")
        back = recognize(parse(stored))
        assert not isinstance(back, Unrecognized), back
        assert replace(back, layer=recipe.layer, style_name=recipe.style_name) == recipe
    finally:
        request("DELETE", f"/rest/styles/{name}?purge=true")


def test_geoserver_draws_the_sld_without_text() -> None:
    (layer, bbox), recipe = CASES["choropleth"]
    body = strip_text(write(recipe.to_layer()))
    assert "TextSymbolizer" not in body
    status, kind, image = get_map(layer, bbox, SLD_BODY=body)
    assert (status, kind) == (200, "image/png"), image[:500]
