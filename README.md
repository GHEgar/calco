# calco

Write and parse [SLD](https://www.ogc.org/standard/sld/) styles both ways, and translate SLD labels
to [MapLibre](https://maplibre.org/) symbol layers.

- **Round trip as a contract**: every recipe satisfies `recognize(parse(write(style))) == style`.
- **Nothing is lost silently**: whatever the reader does not understand is reported with its path.
- **No runtime dependencies**: the standard library's `xml.etree` and frozen dataclasses.
- Writes SLD 1.0.0, the version GeoServer handles best; reads SLD 1.0.0 and SLD 1.1 / SE 1.1.
- Classification (quantile, Jenks, equal interval, standard deviation) ported from
  `@ghegar/panal/classify` and checked against its test vectors.

```bash
pip install calco
```

Requires Python 3.12 or newer.

## Recipes

### Choropleth by ranges

Classes are `[lower, upper)` with the last one closed; the first lower bound and the last upper bound
may be open (`None`). Breaks must be contiguous.

```python
from calco import Choropleth, Hatch, Label, NullStyle, Property, Halo, Stroke, write

style = Choropleth.from_breaks(
    "municipalities",
    "density",
    breaks=[0, 10, 50, None],
    colors=["#FEE5D9", "#FCAE91", "#CB181D"],
    titles=["0 to 10", "10 to 50", "50 or more"],
    stroke=Stroke("#FFFFFF", 0.35),
    null=NullStyle(title="No data", hatch=Hatch("shape://times", "#7A7A7A", size=7)),
    label=Label(Property("name"), halo=Halo(2)),
)
xml = write(style.to_layer())
```

The null rule draws a plain background and a hatch on top, each with its own stroke.

### Classifying the values first

```python
from calco import classify

result = classify(densities, "jenks", classes=5)
style = Choropleth.from_classification("municipalities", "density", result, colors)
```

`classify` supports `quantile`, `jenks`, `equalInterval`, `stdDev` (`std_dev_interval=1` or `0.5`)
and `manual`. `class_of` and `legend` use the same interval rule as the SLD: `>= lower`, `< upper`,
the last class closed. A degenerate last class (`[x, x]`) is allowed, as classification can produce it.

### Categories by value

```python
from calco import Categories, Other

style = Categories.from_values(
    "states",
    "region",
    ["Pacific", "Mountain"],
    ["#1B9E77", "#D95F02"],
    other=Other("#DDDDDD", "Other regions"),
)
```

Each category is an equality rule; `other` becomes an `ElseFilter` rule. Values written as canonical
numbers (`15`) read back as numbers; anything else (`"001"`) stays text.

### Single polygon, lines, points and labels only

```python
from calco import ExternalGraphic, Fill, Graphic, Mark, Point, Polygon, ScaleRange

outline = Polygon(
    "states", fill=None, stroke=Stroke("#333333", 1), scales=ScaleRange(max=5_000_000)
)
hatched = Polygon("reserves", fill=Hatch("shape://slash"), stroke=None)
wells = Point("wells", Graphic(Mark("circle", Fill("#1F77B4"), None), size=8))
icons = Point("schools", Graphic(ExternalGraphic("https://example.org/school.png"), size=16))
roads = Line("roads", (Stroke("#333333", 5), Stroke("#FFD966", 3)))
names = Annotation("cities", Label(Property("name"), halo=Halo(1.5)))
```

A `Line` with several strokes draws them in order, which gives a cased road.

### Geometry and label expressions

Geometries and label contents are expressions: `Property`, `Literal` and `Function`.

```python
from calco import Function, Literal

geometry = Function("property", (Function("env", (Literal("geom"), Literal("the_geom"))),))
label = Label(
    (Literal("Pop. "), Property("population")),
    geometry=Function("centroid", (Property("the_geom"),)),
)
```

Functions in `sld:Geometry` and `VendorOption` are GeoServer extensions: GeoServer accepts them, but
they do not validate against the SLD 1.0.0 schema.

## Parsing

```python
from calco import Unrecognized, parse, recognize

document = parse(xml)
document.all_unsupported
style = recognize(document)
if isinstance(style, Unrecognized):
    print(style.reasons)
```

`parse` returns a generic model (`StyledLayerDescriptor`, `StyledLayer`, `UserStyle`,
`FeatureTypeStyle`, `Rule`, filters and symbolizers) that `write` turns back into XML. `recognize`
tries `Choropleth`, `Categories`, `Polygon`, `Line`, `Point` and `Annotation`, and returns the first that matches with nothing left over,
or `Unrecognized` with the reason each recipe gave.

A WMS `GetStyles` response lists every style of the layer. `recognize(document, "style_name")` picks
one by name; without a name it takes the `IsDefault` one, or the only one. What the reader could not
understand is reported per user style, so a foreign style next to yours does not block it.

### GeoServer notes

- GeoServer reads the whitespace between parts of a `Label` as a single space, and writes styles back
  indented. calco writes labels without indentation and reads them the same way GeoServer does, but a
  style GeoServer re-encodes gains a space next to every literal each time it is rewritten.
- GeoServer renames the layer to `Default Styler` and names the `FeatureTypeStyle` `name` when it
  stores a style; recipes ignore `FeatureTypeStyle` names.

## MapLibre labels

```python
from calco.maplibre import label_layers, strip_text

result = label_layers(parse(xml), source="municipalities", source_layer=None)
result.layers
result.skipped
result.notes

wms_body = strip_text(xml)
```

Every `TextSymbolizer` becomes a `symbol` layer with native `text-*` properties: content, font, color,
halo, anchor, displacement, line placement, scale denominators as `minzoom`/`maxzoom`, filters and
`ElseFilter`, and the vendor options that have an equivalent (`autoWrap`, `spaceAround`, `followLine`,
`repeat`, `conflictResolution`, `maxAngleDelta`). Label functions with an exact equivalent are
translated: `Concatenate`, `strToUpperCase`, `strToLowerCase`, `strSubstring`, `strSubstringStart`,
and `numberFormat` when its pattern groups digits (MapLibre always does). A rule that cannot be
translated faithfully is skipped and reported instead of drawn wrong.

`text-font` must name a fontstack your glyph server has. The default is `"<family> <Regular|Bold|
Italic|Bold Italic>"`; pass `fonts=lambda font: [...]` to map them yourself.

`strip_text` removes the `TextSymbolizer` elements from an SLD, so a WMS can draw the rest while
MapLibre draws the labels.

`scale_to_zoom` and `zoom_to_scale` convert with the OGC 0.28 mm pixel and 512 px tiles by default.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check . && ruff format --check .
mypy
```

Tests marked `geoserver` run against a live GeoServer with its sample data, and are skipped
otherwise:

```bash
docker run -d --rm --name calco-geoserver -p 8599:8080 -e SAMPLE_DATA=true \
    -e GEOSERVER_ADMIN_PASSWORD=geoserver kartoza/geoserver:3.0.0
CALCO_GEOSERVER_URL=http://localhost:8599/geoserver pytest -m geoserver
```

## License

[AGPL-3.0-only](LICENSE)
