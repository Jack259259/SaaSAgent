"""{{占位符}} 提取(供 sopcheck 闭合/定义校验)与解析(供执行期取值)。"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")
_EXACT_RE = re.compile(r"^\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}$")


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _walk_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _walk_strings(v)]
    return []


def placeholders_in(value: Any) -> set[str]:
    """递归收集所有 {{name}} 的 name。"""
    names: set[str] = set()
    for text in _walk_strings(value):
        names.update(_PLACEHOLDER_RE.findall(text))
    return names


def has_unbalanced_braces(value: Any) -> bool:
    """任一字符串内 `{{` 与 `}}` 数量不等 → 视为未闭合。"""
    return any(text.count("{{") != text.count("}}") for text in _walk_strings(value))


def resolve(value: Any, context: dict[str, Any]) -> Any:
    """用 context 解析占位符。整串恰为一个占位符时保留原值类型;否则做字符串插值。"""
    if isinstance(value, dict):
        return {k: resolve(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, context) for v in value]
    if not isinstance(value, str):
        return value
    exact = _EXACT_RE.match(value)
    if exact:
        return context[exact.group(1)]  # 缺失 → KeyError(执行期暴露为校验失败)
    return _PLACEHOLDER_RE.sub(lambda m: str(context[m.group(1)]), value)
