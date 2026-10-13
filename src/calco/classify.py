from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

Method = Literal["quantile", "jenks", "equalInterval", "stdDev", "manual"]
METHODS: tuple[str, ...] = ("quantile", "jenks", "equalInterval", "stdDev", "manual")
DEFAULT_CLASSES = 5
JENKS_SAMPLE_SIZE = 4000
STD_DEV_LIMIT = 3


@dataclass(frozen=True)
class ValueStats:
    n: int
    min: float
    max: float
    mean: float
    std_dev: float


@dataclass(frozen=True)
class Classification:
    method: str
    breaks: tuple[float, ...]
    requested: int
    actual: int
    stats: ValueStats


@dataclass(frozen=True)
class LegendEntry:
    class_index: int
    min: float
    max: float
    count: int
    closed: Literal["left", "both"]


def finite_sorted(values: Iterable[float | None]) -> list[float]:
    return sorted(
        value
        for value in values
        if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
    )


def compute_stats(ordered: list[float]) -> ValueStats:
    n = len(ordered)
    if n == 0:
        return ValueStats(0, math.nan, math.nan, math.nan, math.nan)
    total = 0.0
    for value in ordered:
        total += value
    mean = total / n
    squares = 0.0
    for value in ordered:
        squares += (value - mean) ** 2
    return ValueStats(n, ordered[0], ordered[-1], mean, math.sqrt(squares / n))


def quantile_breaks(ordered: list[float], classes: int) -> list[float]:
    last = len(ordered) - 1
    breaks: list[float] = []
    for index in range(classes + 1):
        position = (last * index) / classes
        lower = math.floor(position)
        fraction = position - lower
        base = ordered[lower]
        breaks.append(base if fraction == 0 else base + (ordered[lower + 1] - base) * fraction)
    return breaks


def equal_interval_breaks(low: float, high: float, classes: int) -> list[float]:
    step = (high - low) / classes
    return [low + step * index for index in range(classes)] + [high]


def std_dev_breaks(stats: ValueStats, interval: float) -> list[float]:
    if not stats.std_dev > 0:
        return [stats.min, stats.max]
    inner: list[float] = []
    z = interval / 2
    while z <= STD_DEV_LIMIT:
        inner += [stats.mean - z * stats.std_dev, stats.mean + z * stats.std_dev]
        z += interval
    kept = sorted(value for value in inner if stats.min < value < stats.max)
    return [stats.min, *kept, stats.max]


def jenks_sample(ordered: list[float]) -> list[float]:
    if len(ordered) <= JENKS_SAMPLE_SIZE:
        return list(ordered)
    last = len(ordered) - 1
    return [
        ordered[_round_half_up((index * last) / (JENKS_SAMPLE_SIZE - 1))]
        for index in range(JENKS_SAMPLE_SIZE)
    ]


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _lower_class_limits(data: list[float], classes: int) -> list[int]:
    n = len(data)
    width = classes + 1
    lower = [0] * ((n + 1) * width)
    variance = [math.inf] * ((n + 1) * width)
    for j in range(1, classes + 1):
        lower[width + j] = 1
        variance[width + j] = 0.0
    for size in range(2, n + 1):
        total = 0.0
        squares = 0.0
        for m in range(1, size + 1):
            start = size - m + 1
            value = data[start - 1]
            total += value
            squares += value * value
            own = squares - (total * total) / m
            previous = start - 1
            if previous == 0:
                continue
            for j in range(2, classes + 1):
                candidate = own + variance[previous * width + j - 1]
                if variance[size * width + j] >= candidate:
                    lower[size * width + j] = start
                    variance[size * width + j] = candidate
        lower[size * width + 1] = 1
        variance[size * width + 1] = squares - (total * total) / size
    return lower


def jenks_breaks(ordered: list[float], classes: int) -> list[float]:
    data = jenks_sample(ordered)
    k = min(classes, len(data))
    width = k + 1
    lower = _lower_class_limits(data, k)
    breaks = [0.0] * (k + 1)
    breaks[0] = data[0]
    breaks[k] = data[-1]
    end = len(data)
    for j in range(k, 1, -1):
        start = lower[end * width + j]
        breaks[j - 1] = data[start - 1]
        end = start - 1
    return breaks


def _collapse(breaks: list[float]) -> tuple[float, ...]:
    result: list[float] = []
    for value in breaks[:-1]:
        if not result or value > result[-1]:
            result.append(value)
    result.append(breaks[-1])
    return tuple(result)


def _manual(breaks: Iterable[float] | None) -> tuple[float, ...]:
    found = tuple(breaks or ())
    if len(found) < 2:
        raise ValueError("manual classification needs at least two breaks")
    for index, value in enumerate(found):
        if not math.isfinite(value):
            raise ValueError("manual breaks must be finite")
        if index > 0 and value <= found[index - 1]:
            raise ValueError("manual breaks must be strictly increasing")
    return found


def classify(
    values: Iterable[float | None],
    method: Method,
    *,
    classes: int | None = None,
    breaks: Iterable[float] | None = None,
    std_dev_interval: float = 1,
) -> Classification:
    if method not in METHODS:
        raise ValueError(f"method must be one of {', '.join(METHODS)}")
    ordered = finite_sorted(values)
    stats = compute_stats(ordered)
    if method == "manual":
        manual = _manual(breaks)
        return Classification(method, manual, len(manual) - 1, len(manual) - 1, stats)
    requested = DEFAULT_CLASSES if classes is None else classes
    if isinstance(requested, bool) or not isinstance(requested, int) or requested < 1:
        raise ValueError("classes must be a positive integer")
    if std_dev_interval not in (1, 0.5):
        raise ValueError("std_dev_interval must be 1 or 0.5")
    if stats.n == 0:
        return Classification(method, (), requested, 0, stats)
    if stats.min == stats.max:
        raw = [stats.min, stats.max]
    elif method == "quantile":
        raw = quantile_breaks(ordered, requested)
    elif method == "jenks":
        raw = jenks_breaks(ordered, requested)
    elif method == "equalInterval":
        raw = equal_interval_breaks(stats.min, stats.max, requested)
    else:
        raw = std_dev_breaks(stats, std_dev_interval)
    found = _collapse(raw)
    actual = len(found) - 1
    return Classification(method, found, actual if method == "stdDev" else requested, actual, stats)


def class_of(value: float | None, breaks: tuple[float, ...] | list[float]) -> int:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        return -1
    if len(breaks) < 2 or value < breaks[0] or value > breaks[-1]:
        return -1
    last = len(breaks) - 1
    for index in range(last - 1):
        if value < breaks[index + 1]:
            return index
    return last - 1


def legend(
    breaks: tuple[float, ...] | list[float], values: Iterable[float | None] | None = None
) -> list[LegendEntry]:
    counts = [0] * max(len(breaks) - 1, 0)
    for value in values or ():
        index = class_of(value, breaks)
        if index >= 0:
            counts[index] += 1
    return [
        LegendEntry(index, breaks[index], breaks[index + 1], counts[index], _closed(index, breaks))
        for index in range(len(counts))
    ]


def _closed(index: int, breaks: tuple[float, ...] | list[float]) -> Literal["left", "both"]:
    return "both" if index == len(breaks) - 2 else "left"
