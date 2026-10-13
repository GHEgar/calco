from __future__ import annotations

from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from calco.errors import InvalidModel, ParseError
from calco.filters import read_filter, write_filter
from calco.model import (
    FeatureTypeStyle,
    Rule,
    ScaleRange,
    StyledLayer,
    StyledLayerDescriptor,
    UserStyle,
)
from calco.symbolizer_io import SYMBOLIZER_TAGS, read_symbolizer, write_symbolizer
from calco.symbolizers import Symbolizer
from calco.xmltools import PREFIXES, SLD, Children, Reader, local, sub, sub_number

DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'
RULE_CHILDREN = (
    "Name",
    "Title",
    "Abstract",
    "Description",
    "Filter",
    "ElseFilter",
    "MinScaleDenominator",
    "MaxScaleDenominator",
    *SYMBOLIZER_TAGS,
)


def write(source: StyledLayerDescriptor | StyledLayer, *, pretty: bool = True) -> str:
    for prefix, uri in PREFIXES.items():
        ElementTree.register_namespace(prefix, uri)
    layers = source.layers if isinstance(source, StyledLayerDescriptor) else (source,)
    root = Element(f"{{{SLD}}}StyledLayerDescriptor", {"version": "1.0.0"})
    for layer in layers:
        _write_layer(root, layer)
    if pretty:
        ElementTree.indent(root, "  ")
        _tighten_labels(root)
    body = ElementTree.tostring(root, encoding="unicode")
    return f"{DECLARATION}\n{body}\n" if pretty else DECLARATION + body


def _tighten_labels(root: Element) -> None:
    for label in root.iter(f"{{{SLD}}}Label"):
        label.text = None
        for part in label:
            part.tail = None


def _write_layer(root: Element, layer: StyledLayer) -> None:
    named = sub(root, SLD, "NamedLayer")
    sub(named, SLD, "Name", layer.name)
    if layer.named_style is not None:
        sub(sub(named, SLD, "NamedStyle"), SLD, "Name", layer.named_style)
        return
    for user_style in layer.user_styles:
        user = sub(named, SLD, "UserStyle")
        for tag, value in (
            ("Name", user_style.name),
            ("Title", user_style.title),
            ("Abstract", user_style.abstract),
        ):
            if value is not None:
                sub(user, SLD, tag, value)
        if user_style.is_default:
            sub(user, SLD, "IsDefault", "1")
        for style in user_style.styles:
            node = sub(user, SLD, "FeatureTypeStyle")
            if style.name is not None:
                sub(node, SLD, "Name", style.name)
            for rule in style.rules:
                _write_rule(node, rule)


def _write_rule(parent: Element, rule: Rule) -> None:
    node = sub(parent, SLD, "Rule")
    for tag, value in (("Name", rule.name), ("Title", rule.title), ("Abstract", rule.abstract)):
        if value is not None:
            sub(node, SLD, tag, value)
    if rule.filter is not None:
        write_filter(node, rule.filter)
    if rule.else_filter:
        sub(node, SLD, "ElseFilter")
    if rule.scales.min is not None:
        sub_number(node, "MinScaleDenominator", rule.scales.min)
    if rule.scales.max is not None:
        sub_number(node, "MaxScaleDenominator", rule.scales.max)
    for symbolizer in rule.symbolizers:
        write_symbolizer(node, symbolizer)


def parse(xml: str | bytes) -> StyledLayerDescriptor:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ParseError(f"invalid XML: {exc}") from exc
    if local(root.tag) != "StyledLayerDescriptor":
        raise ParseError(f"root element is {local(root.tag)}, not StyledLayerDescriptor")
    reader = Reader()
    groups = reader.children(root, "StyledLayerDescriptor", ("NamedLayer", "Name", "Title"))
    for tag in ("Name", "Title"):
        for _, path in groups.get(tag, []):
            reader.note(path, "descriptor metadata is not kept")
    layers = [_read_layer(elem, path) for elem, path in groups.get("NamedLayer", [])]
    if not layers:
        raise ParseError("no NamedLayer could be read")
    found = [layer for layer in layers if isinstance(layer, StyledLayer)]
    for layer in layers:
        if isinstance(layer, str):
            reader.note("StyledLayerDescriptor", layer)
    if not found:
        raise ParseError("no NamedLayer could be read: " + "; ".join(reader.unsupported))
    return StyledLayerDescriptor(tuple(found), tuple(reader.unsupported))


def _read_layer(elem: Element, path: str) -> StyledLayer | str:
    reader = Reader()
    groups = reader.children(elem, path, ("Name", "NamedStyle", "UserStyle"))
    name = reader.text(groups, "Name")
    if not name:
        return f"{path}: NamedLayer without Name"
    named = reader.one(groups, "NamedStyle")
    users = groups.get("UserStyle", [])
    if users and named is not None:
        reader.note(named[1], "NamedStyle next to a UserStyle is ignored")
    if not users:
        if named is None:
            return f"{path}: NamedLayer without style"
        inner = reader.children(named[0], named[1], ("Name",))
        style = reader.text(inner, "Name")
        if not style:
            return f"{named[1]}: NamedStyle without Name"
        return StyledLayer(name, named_style=style, unsupported=tuple(reader.unsupported))
    read = [_read_user_style(*item) for item in users]
    for item in read:
        if isinstance(item, list):
            reader.unsupported.extend(item)
    kept = tuple(style for style in read if isinstance(style, UserStyle))
    if not kept:
        return f"{path}: no UserStyle could be read"
    return StyledLayer(name, kept, unsupported=tuple(reader.unsupported))


def _read_user_style(elem: Element, path: str) -> UserStyle | list[str]:
    reader = Reader()
    inner = reader.children(
        elem, path, ("Name", "Title", "Abstract", "Description", "IsDefault", "FeatureTypeStyle")
    )
    styles = [_read_style(reader, *item) for item in inner.get("FeatureTypeStyle", [])]
    kept = tuple(style for style in styles if style is not None)
    if not kept:
        reader.note(path, "user style dropped: no FeatureTypeStyle could be read")
        return reader.unsupported
    default = (reader.text(inner, "IsDefault") or "").lower() in ("1", "true")
    return UserStyle(
        kept,
        name=reader.text(inner, "Name"),
        **_describe(reader, inner),
        is_default=default,
        unsupported=tuple(reader.unsupported),
    )


def _read_style(reader: Reader, elem: Element, path: str) -> FeatureTypeStyle | None:
    groups = reader.children(elem, path, ("Name", "Rule", "Description", "FeatureTypeName"))
    for tag in ("Description", "FeatureTypeName"):
        for _, ignored in groups.get(tag, []):
            reader.note(ignored, "FeatureTypeStyle metadata is not kept")
    rules = [_read_rule(reader, *item) for item in groups.get("Rule", [])]
    kept = tuple(rule for rule in rules if rule is not None)
    if not kept:
        reader.note(path, "no Rule could be read")
        return None
    return FeatureTypeStyle(kept, name=reader.text(groups, "Name"))


def _read_rule(reader: Reader, elem: Element, path: str) -> Rule | None:
    groups = reader.children(elem, path, RULE_CHILDREN)
    order = list(elem)
    nodes = sorted(
        (item for tag in SYMBOLIZER_TAGS for item in groups.get(tag, [])),
        key=lambda item: order.index(item[0]),
    )
    symbolizers: list[Symbolizer] = []
    for node, node_path in nodes:
        symbolizer = read_symbolizer(reader, node, node_path)
        if symbolizer is not None:
            symbolizers.append(symbolizer)
    filter_node = reader.one(groups, "Filter")
    rule_filter = None if filter_node is None else read_filter(reader, *filter_node)
    if filter_node is not None and rule_filter is None:
        reader.note(path, "rule dropped: its filter could not be read")
        return None
    if not symbolizers:
        reader.note(path, "rule dropped: no symbolizer could be read")
        return None
    try:
        return Rule(
            tuple(symbolizers),
            name=reader.text(groups, "Name"),
            **_describe(reader, groups),
            filter=rule_filter,
            else_filter=reader.one(groups, "ElseFilter") is not None,
            scales=ScaleRange(
                reader.number(groups, "MinScaleDenominator", None),
                reader.number(groups, "MaxScaleDenominator", None),
            ),
        )
    except InvalidModel as exc:
        reader.note(path, f"rule dropped: {exc}")
        return None


def _describe(reader: Reader, groups: Children) -> dict[str, str | None]:
    found = {"title": reader.text(groups, "Title"), "abstract": reader.text(groups, "Abstract")}
    description = reader.one(groups, "Description")
    if description is None:
        return found
    inner = reader.children(description[0], description[1], ("Title", "Abstract"))
    for key, tag in (("title", "Title"), ("abstract", "Abstract")):
        value = reader.text(inner, tag)
        if value is not None and found[key] is not None:
            reader.note(description[1], f"{tag} given twice; the SE 1.1 Description wins")
        if value is not None:
            found[key] = value
    return found
