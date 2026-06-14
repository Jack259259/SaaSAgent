"""tree-sitter 符号抽取(best-effort)。返回(定义, 引用, 调用边)。

主遍历用显式栈(避免大文件递归超限);callee 名抽取用浅递归取最右标识符。
"""

from __future__ import annotations

from tree_sitter import Node

from .languages import LangSpec, get_parser
from .models import CallEdge, Definition, Reference

_ID_TYPES = frozenset({"identifier", "type_identifier", "field_identifier", "property_identifier"})


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _last_identifier(node: Node, source: bytes) -> str | None:
    """返回 node 子树中最右侧的标识符文本(用于从 callee 表达式取被调名)。"""
    result: str | None = None
    for child in node.children:
        found = _last_identifier(child, source)
        if found is not None:
            result = found
    if result is None and node.type in _ID_TYPES:
        return _text(node, source)
    return result


def _name_of(node: Node, source: bytes) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _text(name_node, source)
    return _last_identifier(node, source)  # SQL 等无 name 字段时回退


def _callee_name(call_node: Node, source: bytes, spec: LangSpec) -> str | None:
    target: Node | None = None
    if spec.callee_field is not None:
        target = call_node.child_by_field_name(spec.callee_field)
    return _last_identifier(target or call_node, source)


def extract_symbols(
    file_rel: str, source: bytes, spec: LangSpec
) -> tuple[list[Definition], list[Reference], list[CallEdge]]:
    tree = get_parser(spec.name).parse(source)
    lines = source.decode("utf-8", "replace").splitlines()

    def snippet_at(line_1based: int) -> str:
        idx = line_1based - 1
        return lines[idx].strip()[:160] if 0 <= idx < len(lines) else ""

    defs: list[Definition] = []
    refs: list[Reference] = []
    calls: list[CallEdge] = []

    # 栈元素:(节点, 所在定义名, 所在定义是否 class-like)
    stack: list[tuple[Node, str, bool]] = [(tree.root_node, "<module>", False)]
    while stack:
        node, enc_name, enc_is_class = stack.pop()
        next_name, next_is_class = enc_name, enc_is_class
        ntype = node.type

        if ntype in spec.def_kinds:
            name = _name_of(node, source)
            if name:
                kind = spec.def_kinds[ntype]
                if kind == "function" and enc_is_class:
                    kind = "method"
                start = node.start_point[0] + 1
                end = node.end_point[0] + 1
                defs.append(
                    Definition(
                        name=name,
                        kind=kind,
                        language=spec.name,
                        file=file_rel,
                        start_line=start,
                        end_line=end,
                        snippet=snippet_at(start),
                    )
                )
                next_name = name
                next_is_class = ntype in spec.class_types
        elif ntype in spec.call_types:
            callee = _callee_name(node, source, spec)
            if callee:
                line = node.start_point[0] + 1
                calls.append(
                    CallEdge(
                        caller=enc_name,
                        callee=callee,
                        file=file_rel,
                        line=line,
                        snippet=snippet_at(line),
                    )
                )
        elif ntype in _ID_TYPES and node.is_named:
            line = node.start_point[0] + 1
            refs.append(
                Reference(
                    name=_text(node, source), file=file_rel, line=line, snippet=snippet_at(line)
                )
            )

        for child in reversed(node.children):
            stack.append((child, next_name, next_is_class))

    return defs, refs, calls
