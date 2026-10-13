from __future__ import annotations

import math
import re
from decimal import Decimal

from calco.errors import InvalidModel

Number = int | float

_SAFE_INTEGER = 2**53
_HEX = re.compile(r"(?:#|0[xX])?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})")
_NUMERIC = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")
_FORBIDDEN = re.compile("[\x00-\x08\x0b-\x1f\x7f\ud800-\udfff￾￿]")


def set_field(target: object, name: str, value: object) -> None:
    object.__setattr__(target, name, value)


def to_number(value: object, field: str) -> Number:
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        raise InvalidModel(f"{field} must be a number, got {value!r}")
    if isinstance(value, int):
        return value if abs(value) < _SAFE_INTEGER else _to_float(value, field)
    as_float = _to_float(value, field)
    if as_float.is_integer() and abs(as_float) < _SAFE_INTEGER:
        return int(as_float)
    return as_float


def _to_float(value: int | float | Decimal, field: str) -> float:
    try:
        as_float = float(value)
    except OverflowError as exc:
        raise InvalidModel(f"{field} is too large: {value!r}") from exc
    if not math.isfinite(as_float):
        raise InvalidModel(f"{field} must be finite, got {value!r}")
    return as_float


def optional_number(value: object, field: str) -> Number | None:
    return None if value is None else to_number(value, field)


def in_range(value: object, field: str, low: float, high: float) -> Number:
    number = to_number(value, field)
    if not low <= number <= high:
        raise InvalidModel(f"{field} must be between {low} and {high}, got {number}")
    return number


def non_negative(value: object, field: str) -> Number:
    return in_range(value, field, 0, math.inf)


def format_number(value: Number) -> str:
    if isinstance(value, int):
        return str(value)
    text = format(Decimal(repr(value)), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def parse_number(text: str) -> Number | None:
    stripped = text.strip()
    if not _NUMERIC.fullmatch(stripped):
        return None
    try:
        if stripped.lstrip("+-").isdigit():
            return to_number(int(stripped), "value")
        return to_number(float(stripped), "value")
    except InvalidModel:
        return None


def literal_value(value: object, field: str) -> Number | str:
    if isinstance(value, str):
        check_text(value, field)
        number = parse_number(value)
        return number if number is not None and format_number(number) == value else value
    return to_number(value, field)


def to_color(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise InvalidModel(f"{field} must be a hex color, got {value!r}")
    match = _HEX.fullmatch(value.strip())
    if match is None:
        raise InvalidModel(f"{field} must be #RRGGBB, got {value!r}")
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(char * 2 for char in digits)
    return "#" + digits.upper()


def check_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise InvalidModel(f"{field} must be a string, got {value!r}")
    if _FORBIDDEN.search(value):
        raise InvalidModel(f"{field} has characters XML cannot carry: {value!r}")
    return value


def clean_text(value: object, field: str) -> str:
    return check_text(value, field).strip()


def required_text(value: object, field: str) -> str:
    text = clean_text(value, field)
    if not text:
        raise InvalidModel(f"{field} must not be empty")
    return text


def optional_text(value: object, field: str) -> str | None:
    return None if value is None else clean_text(value, field)


def choice(value: object, field: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise InvalidModel(f"{field} must be one of {', '.join(allowed)}, got {value!r}")
    return str(value)
