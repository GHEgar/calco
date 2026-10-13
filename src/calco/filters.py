from __future__ import annotations

from dataclasses import dataclass
from typing import Literal as Choice
from xml.etree.ElementTree import Element

from calco.errors import InvalidModel
from calco.values import (
    Number,
    check_text,
    format_number,
    literal_value,
    parse_number,
    required_text,
    set_field,
    to_number,
)
from calco.xmltools import OGC, Reader, local, sub

Operator = Choice["=", "!=", "<", "<=", ">", ">="]

TAGS: dict[Operator, str] = {
    "=": "PropertyIsEqualTo",
    "!=": "PropertyIsNotEqualTo",
    "<": "PropertyIsLessThan",
    "<=": "PropertyIsLessThanOrEqualTo",
    ">": "PropertyIsGreaterThan",
    ">=": "PropertyIsGreaterThanOrEqualTo",
}
OPERATORS: dict[str, Operator] = {tag: operator for operator, tag in TAGS.items()}


@dataclass(frozen=True)
class IsNull:
    property: str

    def __post_init__(self) -> None:
        set_field(self, "property", required_text(self.property, "IsNull.property"))


@dataclass(frozen=True)
class Compare:
    property: str
    operator: Operator
    value: Number | str

    def __post_init__(self) -> None:
        set_field(self, "property", required_text(self.property, "Compare.property"))
        if self.operator not in TAGS:
            raise InvalidModel(f"Compare.operator must be one of {', '.join(TAGS)}")
        set_field(self, "value", literal_value(self.value, "Compare.value"))


@dataclass(frozen=True)
class And:
    operands: tuple[Filter, ...]

    def __post_init__(self) -> None:
        set_field(self, "operands", _operands(self.operands, "And"))


@dataclass(frozen=True)
class Or:
    operands: tuple[Filter, ...]

    def __post_init__(self) -> None:
        set_field(self, "operands", _operands(self.operands, "Or"))


@dataclass(frozen=True)
class Not:
    operand: Filter

    def __post_init__(self) -> None:
        if not isinstance(self.operand, FILTER_TYPES):
            raise InvalidModel("Not.operand must be a filter")


@dataclass(frozen=True)
class Between:
    property: str
    lower: Number
    upper: Number

    def __post_init__(self) -> None:
        set_field(self, "property", required_text(self.property, "Between.property"))
        set_field(self, "lower", to_number(self.lower, "Between.lower"))
        set_field(self, "upper", to_number(self.upper, "Between.upper"))


@dataclass(frozen=True)
class Like:
    property: str
    pattern: str
    wildcard: str = "*"
    single_char: str = "."
    escape: str = "!"

    def __post_init__(self) -> None:
        set_field(self, "property", required_text(self.property, "Like.property"))
        set_field(self, "pattern", check_text(self.pattern, "Like.pattern"))
        marks = []
        for name in ("wildcard", "single_char", "escape"):
            value = check_text(getattr(self, name), f"Like.{name}")
            if len(value) != 1:
                raise InvalidModel(f"Like.{name} must be a single character")
            marks.append(value)
        if len(set(marks)) != 3:
            raise InvalidModel("Like wildcard, single_char and escape must differ")


Filter = IsNull | Compare | Between | Like | And | Or | Not
FILTER_TYPES = (IsNull, Compare, Between, Like, And, Or, Not)


def _operands(value: object, field: str) -> tuple[Filter, ...]:
    if not isinstance(value, tuple | list) or len(value) < 2:
        raise InvalidModel(f"{field} needs at least two operands")
    for item in value:
        if not isinstance(item, FILTER_TYPES):
            raise InvalidModel(f"{field} has a non-filter operand: {item!r}")
    return tuple(value)


def write_filter(parent: Element, rule_filter: Filter) -> None:
    _write_operation(sub(parent, OGC, "Filter"), rule_filter)


def _write_operation(parent: Element, rule_filter: Filter) -> None:
    if isinstance(rule_filter, IsNull):
        node = sub(parent, OGC, "PropertyIsNull")
        sub(node, OGC, "PropertyName", rule_filter.property)
    elif isinstance(rule_filter, Compare):
        node = sub(parent, OGC, TAGS[rule_filter.operator])
        sub(node, OGC, "PropertyName", rule_filter.property)
        value = rule_filter.value
        sub(node, OGC, "Literal", value if isinstance(value, str) else format_number(value))
    elif isinstance(rule_filter, Between):
        node = sub(parent, OGC, "PropertyIsBetween")
        sub(node, OGC, "PropertyName", rule_filter.property)
        sub(sub(node, OGC, "LowerBoundary"), OGC, "Literal", format_number(rule_filter.lower))
        sub(sub(node, OGC, "UpperBoundary"), OGC, "Literal", format_number(rule_filter.upper))
    elif isinstance(rule_filter, Like):
        node = sub(parent, OGC, "PropertyIsLike")
        node.set("wildCard", rule_filter.wildcard)
        node.set("singleChar", rule_filter.single_char)
        node.set("escape", rule_filter.escape)
        sub(node, OGC, "PropertyName", rule_filter.property)
        sub(node, OGC, "Literal", rule_filter.pattern)
    elif isinstance(rule_filter, Not):
        _write_operation(sub(parent, OGC, "Not"), rule_filter.operand)
    else:
        node = sub(parent, OGC, "And" if isinstance(rule_filter, And) else "Or")
        for operand in rule_filter.operands:
            _write_operation(node, operand)


def read_filter(reader: Reader, elem: Element, path: str) -> Filter | None:
    nodes = [child for child in elem if isinstance(child.tag, str)]
    if len(nodes) != 1:
        reader.note(path, "Filter must hold exactly one operation")
        return None
    return _read_operation(reader, nodes[0], f"{path}/{local(nodes[0].tag)}")


def _read_operation(reader: Reader, elem: Element, path: str) -> Filter | None:
    name = local(elem.tag)
    nodes = [child for child in elem if isinstance(child.tag, str)]
    if name in ("And", "Or"):
        operands = [
            _read_operation(reader, node, f"{path}/{local(node.tag)}[{index}]")
            for index, node in enumerate(nodes, start=1)
        ]
        if any(operand is None for operand in operands) or len(operands) < 2:
            reader.note(path, f"{name} with unreadable or too few operands")
            return None
        found = tuple(operand for operand in operands if operand is not None)
        return And(found) if name == "And" else Or(found)
    if name == "Not":
        if len(nodes) != 1:
            reader.note(path, "Not must hold one operation")
            return None
        inner = _read_operation(reader, nodes[0], f"{path}/{local(nodes[0].tag)}")
        return None if inner is None else Not(inner)
    if name == "PropertyIsLike":
        return _read_like(reader, elem, nodes, path)
    if name == "PropertyIsBetween":
        return _read_between(reader, nodes, path)
    if name == "PropertyIsNull":
        prop = _property(nodes, 1)
        if prop is None:
            reader.note(path, "PropertyIsNull must hold one PropertyName")
            return None
        return IsNull(prop)
    if name in OPERATORS:
        return _read_compare(reader, nodes, name, path)
    reader.note(path, "filter operation not supported")
    return None


def _read_compare(reader: Reader, nodes: list[Element], name: str, path: str) -> Filter | None:
    prop = _property(nodes, 2)
    if prop is None or local(nodes[1].tag) != "Literal" or len(nodes[1]):
        reader.note(path, "comparison must be PropertyName then a plain Literal")
        return None
    return Compare(prop, OPERATORS[name], nodes[1].text or "")


def _property(nodes: list[Element], count: int) -> str | None:
    if len(nodes) != count or local(nodes[0].tag) != "PropertyName" or len(nodes[0]):
        return None
    text = (nodes[0].text or "").strip()
    return text or None


def _read_between(reader: Reader, nodes: list[Element], path: str) -> Filter | None:
    prop = _property(nodes, 3)
    bounds: list[Number] = []
    for node, tag in zip(nodes[1:], ("LowerBoundary", "UpperBoundary"), strict=False):
        inner = list(node)
        if local(node.tag) != tag or len(inner) != 1 or local(inner[0].tag) != "Literal":
            break
        value = parse_number(inner[0].text or "")
        if value is None:
            break
        bounds.append(value)
    if prop is None or len(bounds) != 2:
        reader.note(path, "PropertyIsBetween needs a PropertyName and two numeric boundaries")
        return None
    return Between(prop, bounds[0], bounds[1])


def _read_like(reader: Reader, elem: Element, nodes: list[Element], path: str) -> Filter | None:
    prop = _property(nodes, 2)
    if prop is None or local(nodes[1].tag) != "Literal" or len(nodes[1]):
        reader.note(path, "PropertyIsLike must be PropertyName then a plain Literal")
        return None
    escape = elem.get("escape") or elem.get("escapeChar") or "!"
    try:
        return Like(
            prop,
            nodes[1].text or "",
            elem.get("wildCard") or "*",
            elem.get("singleChar") or ".",
            escape,
        )
    except InvalidModel as exc:
        reader.note(path, str(exc))
        return None
