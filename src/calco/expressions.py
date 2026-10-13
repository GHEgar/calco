from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree.ElementTree import Element

from calco.errors import InvalidModel
from calco.values import check_text, required_text, set_field
from calco.xmltools import OGC, Reader, local, sub

_INDENT_START = re.compile(r"^[ \t]*\n\s*")
_INDENT_END = re.compile(r"\n\s*$")
_INDENT_INNER = re.compile(r"\n\s*")


@dataclass(frozen=True)
class Property:
    name: str

    def __post_init__(self) -> None:
        set_field(self, "name", required_text(self.name, "Property.name"))


@dataclass(frozen=True)
class Literal:
    value: str

    def __post_init__(self) -> None:
        set_field(self, "value", check_text(self.value, "Literal.value"))


@dataclass(frozen=True)
class Function:
    name: str
    args: tuple[Expression, ...] = ()

    def __post_init__(self) -> None:
        set_field(self, "name", required_text(self.name, "Function.name"))
        set_field(self, "args", as_expressions(self.args, "Function.args", allow_empty=True))


Expression = Property | Literal | Function


def as_expressions(
    value: object, field: str, *, allow_empty: bool = False
) -> tuple[Expression, ...]:
    items = (value,) if isinstance(value, Property | Literal | Function) else value
    if not isinstance(items, tuple | list):
        raise InvalidModel(f"{field} must be an expression or a sequence of expressions")
    for item in items:
        if not isinstance(item, Property | Literal | Function):
            raise InvalidModel(f"{field} has a non-expression item: {item!r}")
    if not items and not allow_empty:
        raise InvalidModel(f"{field} must not be empty")
    return tuple(items)


def optional_expression(value: object, field: str) -> Expression | None:
    if value is None or isinstance(value, Property | Literal | Function):
        return value
    raise InvalidModel(f"{field} must be an expression, got {value!r}")


def write_expression(parent: Element, expression: Expression) -> None:
    if isinstance(expression, Property):
        sub(parent, OGC, "PropertyName", expression.name)
    elif isinstance(expression, Literal):
        sub(parent, OGC, "Literal", expression.value)
    else:
        node = sub(parent, OGC, "Function")
        node.set("name", expression.name)
        for arg in expression.args:
            write_expression(node, arg)


def read_expression(reader: Reader, elem: Element, path: str) -> Expression | None:
    name = local(elem.tag)
    if name == "PropertyName":
        text = (elem.text or "").strip()
        if not text or len(elem):
            reader.note(path, "PropertyName must hold a plain name")
            return None
        return Property(text)
    if name == "Literal":
        if len(elem):
            reader.note(path, "Literal with child elements is not supported")
            return None
        return Literal(elem.text or "")
    if name == "Function":
        return _read_function(reader, elem, path)
    reader.note(path, "expression not supported")
    return None


def _read_function(reader: Reader, elem: Element, path: str) -> Expression | None:
    function_name = (elem.get("name") or "").strip()
    if not function_name:
        reader.note(path, "Function without name")
        return None
    args: list[Expression] = []
    for index, child in enumerate(elem, start=1):
        arg = read_expression(reader, child, f"{path}/{local(child.tag)}[{index}]")
        if arg is None:
            return None
        args.append(arg)
    return Function(function_name, tuple(args))


def read_mixed(reader: Reader, elem: Element, path: str) -> tuple[Expression, ...] | None:
    children = list(elem)
    parts: list[Expression] = []
    _append_text(parts, _INDENT_START.sub("", elem.text or ""), len(children) == 0)
    for index, child in enumerate(children, start=1):
        part = read_expression(reader, child, f"{path}/{local(child.tag)}[{index}]")
        if part is None:
            return None
        parts.append(part)
        _append_text(parts, child.tail or "", index == len(children))
    return tuple(parts)


def _append_text(parts: list[Expression], text: str, last: bool) -> None:
    if last:
        text = _INDENT_END.sub("", text)
    text = _INDENT_INNER.sub(" ", text)
    if text:
        parts.append(Literal(text))


def read_single(reader: Reader, elem: Element, path: str) -> Expression | None:
    nodes = [child for child in elem if isinstance(child.tag, str)]
    if len(nodes) != 1 or (elem.text and elem.text.strip()):
        reader.note(path, "expected exactly one expression")
        return None
    return read_expression(reader, nodes[0], f"{path}/{local(nodes[0].tag)}")
