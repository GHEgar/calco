from __future__ import annotations

import re
from typing import Any

from calco.expressions import Expression, Function, Literal, Property
from calco.filters import And, Between, Compare, Filter, IsNull, Like, Not, Or
from calco.values import parse_number

CONCAT_FUNCTIONS = ("Concatenate", "concatenate", "strConcat", "concat")
CASE_FUNCTIONS = {"strToUpperCase": "upcase", "strToLowerCase": "downcase"}
NUMBER_PATTERN = re.compile(r"(?P<integer>[#,]*0[0,]*)(?:\.(?P<required>0*)(?P<optional>#*))?")
OPERATORS = {"=": "==", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}


class Untranslatable(Exception):
    pass


def _flatten(parts: tuple[Expression, ...]) -> list[Any]:
    found: list[Any] = []
    for part in parts:
        if isinstance(part, Function) and part.name in CONCAT_FUNCTIONS:
            found.extend(_flatten(part.args))
        else:
            found.append(_text(part))
    return found


def _text(part: Expression) -> Any:
    if isinstance(part, Literal):
        return part.value
    if isinstance(part, Property):
        return ["to-string", ["get", part.name]]
    name, args = part.name, part.args
    if name in CONCAT_FUNCTIONS:
        return ["concat", *_flatten(args)]
    if name in CASE_FUNCTIONS and len(args) == 1:
        return [CASE_FUNCTIONS[name], _text(args[0])]
    if name in ("strSubstring", "strSubstringStart") and len(args) == (
        3 if name == "strSubstring" else 2
    ):
        return ["slice", _text(args[0]), *(_index(arg, name) for arg in args[1:])]
    if name == "numberFormat" and len(args) in (2, 3):
        return _number_format(args)
    raise Untranslatable(f"label function {name} has no MapLibre equivalent")


def _index(arg: Expression, name: str) -> int:
    value = parse_number(arg.value) if isinstance(arg, Literal) else None
    if not isinstance(value, int) or value < 0:
        raise Untranslatable(f"{name} needs literal, non-negative integer positions")
    return value


def _number_format(args: tuple[Expression, ...]) -> list[Any]:
    pattern = args[0]
    if not isinstance(pattern, Literal):
        raise Untranslatable("numberFormat needs a literal pattern")
    match = NUMBER_PATTERN.fullmatch(pattern.value.strip())
    if match is None or "," not in match.group("integer"):
        raise Untranslatable(
            f"numberFormat pattern {pattern.value!r} has no MapLibre equivalent: "
            "MapLibre always groups digits and only controls fraction digits"
        )
    required, optional = match.group("required") or "", match.group("optional") or ""
    options: dict[str, Any] = {
        "min-fraction-digits": len(required),
        "max-fraction-digits": len(required) + len(optional),
    }
    if len(args) == 3:
        language = args[2]
        if not isinstance(language, Literal):
            raise Untranslatable("numberFormat needs a literal language")
        options["locale"] = language.value
    value = args[1]
    source = ["get", value.name] if isinstance(value, Property) else _text(value)
    return ["number-format", ["to-number", source], options]


def text_field(parts: tuple[Expression, ...]) -> str | list[Any]:
    flat = _flatten(parts)
    if all(isinstance(item, str) for item in flat):
        return "".join(flat)
    if len(flat) == 1:
        single: list[Any] = flat[0]
        return single
    return ["concat", *flat]


def filter_expression(rule_filter: Filter) -> list[Any]:
    if isinstance(rule_filter, IsNull):
        return ["==", ["get", rule_filter.property], None]
    if isinstance(rule_filter, Compare):
        return [OPERATORS[rule_filter.operator], ["get", rule_filter.property], rule_filter.value]
    if isinstance(rule_filter, Like):
        raise Untranslatable("PropertyIsLike has no MapLibre equivalent")
    if isinstance(rule_filter, Between):
        value = ["get", rule_filter.property]
        return ["all", [">=", value, rule_filter.lower], ["<=", value, rule_filter.upper]]
    if isinstance(rule_filter, Not):
        return ["!", filter_expression(rule_filter.operand)]
    head = "all" if isinstance(rule_filter, And) else "any"
    assert isinstance(rule_filter, And | Or)
    return [head, *(filter_expression(item) for item in rule_filter.operands)]


def else_expression(siblings: tuple[Filter | None, ...]) -> list[Any] | None:
    if any(item is None for item in siblings):
        raise Untranslatable("the ElseFilter never applies: a sibling rule has no filter")
    filters = [filter_expression(item) for item in siblings if item is not None]
    if not filters:
        return None
    return ["!", filters[0] if len(filters) == 1 else ["any", *filters]]
