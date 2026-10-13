from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest

from calco import (
    Choropleth,
    Fill,
    InvalidModel,
    Literal,
    NullStyle,
    Polygon,
    Property,
    RangeClass,
    ScaleRange,
    Stroke,
    TextSymbolizer,
)
from calco.values import format_number, parse_number


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (10, "10"),
        (10.0, "10"),
        (0.1, "0.1"),
        (1e-7, "0.0000001"),
        (-0.0, "0"),
        (1e20, "1" + "0" * 20),
    ],
)
def test_format_number(value: float, text: str) -> None:
    assert format_number(value) == text


def test_numbers_normalize_on_construction() -> None:
    assert Stroke(width=cast(float, Decimal("2.50"))).width == 2.5
    assert Stroke(width=3.0).width == 3
    assert isinstance(Stroke(width=3.0).width, int)
    assert parse_number("1_000") is None
    assert parse_number(" 2.5 ") == 2.5


def test_colors_normalize() -> None:
    assert Fill("#abc").color == "#AABBCC"
    with pytest.raises(InvalidModel):
        Fill("red")


def test_rejects_text_xml_cannot_carry() -> None:
    with pytest.raises(InvalidModel):
        Literal("a\x00b")


def test_from_breaks_builds_contiguous_classes() -> None:
    recipe = Choropleth.from_breaks("l", "a", [None, 1, 2], ["#000000", "#FFFFFF"])
    assert recipe.classes == (RangeClass(None, 1, "#000000"), RangeClass(1, 2, "#FFFFFF"))
    assert recipe.breaks == (None, 1, 2)


@pytest.mark.parametrize(
    "classes",
    [
        (),
        (RangeClass(None, None, "#000000"),),
        (RangeClass(0, 1, "#000000"), RangeClass(2, 3, "#000000")),
        (RangeClass(0, None, "#000000"), RangeClass(None, 3, "#000000")),
    ],
)
def test_choropleth_rejects_bad_classes(classes: tuple[RangeClass, ...]) -> None:
    with pytest.raises(InvalidModel):
        Choropleth("l", "a", classes)


def test_range_class_bounds() -> None:
    with pytest.raises(InvalidModel):
        RangeClass(5, 4, "#000000")
    with pytest.raises(InvalidModel, match="only the last class"):
        Choropleth("l", "a", (RangeClass(1, 1, "#000000"), RangeClass(1, 2, "#000000")))
    last = Choropleth("l", "a", (RangeClass(0, 1, "#000000"), RangeClass(1, 1, "#000000")))
    assert last.breaks == (0, 1, 1)


def test_other_validations() -> None:
    with pytest.raises(InvalidModel):
        ScaleRange(10, 5)
    with pytest.raises(InvalidModel):
        NullStyle(background=None, hatch=None, stroke=None)
    with pytest.raises(InvalidModel):
        Polygon("l", fill=None, stroke=None)
    with pytest.raises(InvalidModel):
        Stroke(opacity=2)
    with pytest.raises(InvalidModel):
        TextSymbolizer(())
    assert TextSymbolizer(Property("a")).parts == (Property("a"),)
