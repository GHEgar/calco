from __future__ import annotations

from typing import Any

from calco.expressions import Expression, Function, Literal, Property
from calco.filters import And, Between, Compare, Filter, IsNull, Not, Or

CONCAT_FUNCTIONS = ("Concatenate", "concatenate", "strConcat", "concat")
OPERATORS = {"=": "==", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}


class Untranslatable(Exception):
    pass


def _flatten(parts: tuple[Expression, ...]) -> list[Any]:
    found: list[Any] = []
    for part in parts:
        if isinstance(part, Property):
            found.append(["to-string", ["get", part.name]])
        elif isinstance(part, Literal):
            found.append(part.value)
        elif isinstance(part, Function) and part.name in CONCAT_FUNCTIONS:
            found.extend(_flatten(part.args))
        else:
            assert isinstance(part, Function)
            raise Untranslatable(f"label function {part.name} has no MapLibre equivalent")
    return found


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
