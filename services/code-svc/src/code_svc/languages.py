"""每语言 node-type 配置 + tree-sitter 解析器加载。

支持 python / javascript / typescript / java / sql。抽取为 best-effort(按 node-type,
非完整 tags.scm 查询),精度差异:
- python:定义/调用/引用较准(method 由所在 class 判定);
- javascript / typescript:函数/方法/类/接口 + call_expression 调用,箭头函数赋值不计为定义;
- java:方法/类/接口/构造器 + method_invocation;
- sql:仅 create_function/table/view 当定义(名称取后代标识符),**无调用边,精度最低**。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from tree_sitter import Language, Parser


@dataclass(frozen=True)
class LangSpec:
    name: str
    extensions: tuple[str, ...]
    def_kinds: dict[str, str]  # tree-sitter node type -> 我方 kind
    class_types: frozenset[str]  # 哪些定义类型"包裹方法"(用于 function->method 判定)
    call_types: frozenset[str]
    callee_field: str | None  # 调用节点上取 callee 的字段(无则后代标识符)


_PYTHON = LangSpec(
    "python",
    (".py", ".pyi"),
    {"function_definition": "function", "class_definition": "class"},
    frozenset({"class_definition"}),
    frozenset({"call"}),
    "function",
)
_JS = LangSpec(
    "javascript",
    (".js", ".jsx", ".mjs", ".cjs"),
    {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "method_definition": "method",
        "class_declaration": "class",
    },
    frozenset({"class_declaration"}),
    frozenset({"call_expression"}),
    "function",
)
_TS = LangSpec(
    "typescript",
    (".ts", ".tsx", ".mts", ".cts"),
    {
        "function_declaration": "function",
        "method_definition": "method",
        "class_declaration": "class",
        "interface_declaration": "interface",
    },
    frozenset({"class_declaration", "interface_declaration"}),
    frozenset({"call_expression"}),
    "function",
)
_JAVA = LangSpec(
    "java",
    (".java",),
    {
        "method_declaration": "method",
        "constructor_declaration": "constructor",
        "class_declaration": "class",
        "interface_declaration": "interface",
    },
    frozenset({"class_declaration", "interface_declaration"}),
    frozenset({"method_invocation"}),
    "name",
)
_SQL = LangSpec(
    "sql",
    (".sql",),
    {"create_function": "function", "create_table": "table", "create_view": "view"},
    frozenset(),
    frozenset(),  # 无调用边
    None,
)

_SPECS: tuple[LangSpec, ...] = (_PYTHON, _JS, _TS, _JAVA, _SQL)
_BY_EXT: dict[str, LangSpec] = {ext: spec for spec in _SPECS for ext in spec.extensions}


def spec_for_path(path: str | Path) -> LangSpec | None:
    return _BY_EXT.get(Path(path).suffix.lower())


def _load_language(name: str) -> Language:
    if name == "python":
        import tree_sitter_python

        return Language(tree_sitter_python.language())
    if name == "javascript":
        import tree_sitter_javascript

        return Language(tree_sitter_javascript.language())
    if name == "typescript":
        import tree_sitter_typescript

        return Language(tree_sitter_typescript.language_typescript())
    if name == "java":
        import tree_sitter_java

        return Language(tree_sitter_java.language())
    if name == "sql":
        import tree_sitter_sql

        return Language(tree_sitter_sql.language())
    raise ValueError(f"未知语言:{name}")


@cache
def get_parser(name: str) -> Parser:
    return Parser(_load_language(name))
