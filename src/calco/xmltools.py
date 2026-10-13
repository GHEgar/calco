from __future__ import annotations

from collections.abc import Iterable
from xml.etree.ElementTree import Element, SubElement

from calco.values import Number, format_number, parse_number

SLD = "http://www.opengis.net/sld"
OGC = "http://www.opengis.net/ogc"
XLINK = "http://www.w3.org/1999/xlink"

PREFIXES = {
    "sld": SLD,
    "ogc": OGC,
    "xlink": XLINK,
    "se": "http://www.opengis.net/se",
    "gml": "http://www.opengis.net/gml",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

Children = dict[str, list[tuple[Element, str]]]


def local(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]


def sub(parent: Element, namespace: str, name: str, text: str | None = None) -> Element:
    node = SubElement(parent, f"{{{namespace}}}{name}")
    if text is not None:
        node.text = text
    return node


def sub_number(parent: Element, name: str, value: Number) -> Element:
    return sub(parent, SLD, name, format_number(value))


def write_params(parent: Element, params: Iterable[tuple[str, str | None]]) -> None:
    for name, value in params:
        if value is not None:
            sub(parent, SLD, "CssParameter", value).set("name", name)


class Reader:
    def __init__(self) -> None:
        self.unsupported: list[str] = []

    def note(self, path: str, message: str) -> None:
        self.unsupported.append(f"{path}: {message}")

    def children(self, elem: Element, path: str, allowed: Iterable[str]) -> Children:
        known = set(allowed)
        groups: Children = {}
        counts: dict[str, int] = {}
        for child in elem:
            if not isinstance(child.tag, str):
                continue
            name = local(child.tag)
            counts[name] = counts.get(name, 0) + 1
            child_path = f"{path}/{name}" + (f"[{counts[name]}]" if counts[name] > 1 else "")
            if name in known:
                groups.setdefault(name, []).append((child, child_path))
            else:
                self.note(child_path, "not supported")
        return groups

    def one(self, groups: Children, name: str) -> tuple[Element, str] | None:
        items = groups.get(name, [])
        for _, extra_path in items[1:]:
            self.note(extra_path, "repeated element ignored")
        return items[0] if items else None

    def text(self, groups: Children, name: str) -> str | None:
        found = self.one(groups, name)
        if found is None:
            return None
        elem, path = found
        if len(elem):
            self.note(path, "expressions are not supported here")
        return (elem.text or "").strip()

    def number(self, groups: Children, name: str, default: Number | None) -> Number | None:
        found = self.one(groups, name)
        if found is None:
            return default
        elem, path = found
        value = None if len(elem) else parse_number(elem.text or "")
        if value is None:
            self.note(path, f"not a plain number, default {default} used")
            return default
        return value

    def params(self, elem: Element, path: str, names: Iterable[str]) -> dict[str, str]:
        known = set(names)
        found: dict[str, str] = {}
        for child in elem:
            name = local(child.tag)
            if name not in ("CssParameter", "SvgParameter"):
                continue
            param = child.get("name", "")
            param_path = f"{path}/{name}[@name='{param}']"
            if param not in known:
                self.note(param_path, "parameter not supported")
            elif len(child):
                self.note(param_path, "expressions are not supported here")
            else:
                found[param] = (child.text or "").strip()
        return found

    def param_number(self, params: dict[str, str], name: str, default: Number, path: str) -> Number:
        if name not in params:
            return default
        value = parse_number(params[name])
        if value is None:
            self.note(path, f"{name} is not a number, default {default} used")
            return default
        return value
