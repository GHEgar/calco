from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from calco import Choropleth, parse, recognize, write
from calco.classify import LegendEntry, class_of, classify, legend

FOLDER = Path(__file__).parent / "fixtures/classify"
VECTORS = [json.loads(path.read_text()) for path in sorted(FOLDER.glob("*.json"))]


def to_number(value: float | str | None) -> float | None:
    return float(value) if isinstance(value, str) else value


def run(vector: dict[str, Any]) -> Any:
    options = vector["options"]
    return classify(
        [to_number(value) for value in vector["values"]],
        options["method"],
        classes=options.get("classes"),
        breaks=options.get("breaks"),
        std_dev_interval=options.get("stdDev", {}).get("interval", 1),
    )


def test_has_vectors() -> None:
    assert len(VECTORS) > 10


@pytest.mark.parametrize("vector", VECTORS, ids=[vector["name"] for vector in VECTORS])
def test_matches_panal_vectors(vector: dict[str, Any]) -> None:
    result = run(vector)
    expected = vector["expected"]
    assert result.requested == expected["requested"]
    assert result.actual == expected["actual"]
    assert len(result.breaks) == len(expected["breaks"])
    for value, wanted in zip(result.breaks, expected["breaks"], strict=True):
        assert abs(value - wanted) <= vector["tolerance"] * max(1, abs(wanted))


def test_class_of_and_legend_share_the_interval_rule() -> None:
    breaks = (0, 10, 20)
    assert [class_of(value, breaks) for value in (-1, 0, 9.99, 10, 20, 21, None, math.nan)] == [
        -1,
        0,
        0,
        1,
        1,
        -1,
        -1,
        -1,
    ]
    assert legend(breaks, [0, 5, 10, 20, 30]) == [
        LegendEntry(0, 0, 10, 2, "left"),
        LegendEntry(1, 10, 20, 2, "both"),
    ]


@pytest.mark.parametrize(
    ("method", "options"),
    [("manual", {"breaks": [1]}), ("manual", {"breaks": [2, 1]}), ("quantile", {"classes": 0})],
)
def test_rejects_bad_options(method: Any, options: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"breaks|classes"):
        classify([1, 2, 3], method, **options)


@pytest.mark.parametrize(
    "name", ["jenks-negatives-4", "equal-interval-constant-3", "std-dev-skewed-half"]
)
def test_classifications_become_choropleths(name: str) -> None:
    vector = next(item for item in VECTORS if item["name"] == name)
    result = run(vector)
    colors = ["#000000"] * result.actual
    recipe = Choropleth.from_classification("capa", "valor", result, colors)
    assert recipe.breaks == result.breaks
    assert recognize(parse(write(recipe.to_layer()))) == recipe


def test_empty_classification_is_rejected() -> None:
    with pytest.raises(ValueError, match="no classes"):
        Choropleth.from_classification("capa", "valor", classify([], "quantile"), [])
