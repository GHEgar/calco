from __future__ import annotations

from xml.etree import ElementTree

from calco.errors import ParseError
from calco.xmltools import PREFIXES, local


def strip_text(xml: str | bytes) -> str:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ParseError(f"invalid XML: {exc}") from exc
    for parent in list(root.iter()):
        for child in list(parent):
            if local(child.tag) == "TextSymbolizer":
                parent.remove(child)
    for elem in root.iter():
        if len(elem) and elem.text is not None and not elem.text.strip():
            elem.text = None
        if elem.tail is not None and not elem.tail.strip():
            elem.tail = None
    for prefix, uri in PREFIXES.items():
        ElementTree.register_namespace(prefix, uri)
    return ElementTree.tostring(root, encoding="unicode")
