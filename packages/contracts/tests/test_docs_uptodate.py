"""docs/tools/README.md 必须与 docgen 重渲染一致(要求 9:自动生成 + 防漂移)。

read_text 默认通用换行(CRLF→LF),故对 Windows 行尾稳健。
"""

from __future__ import annotations

from contracts.docgen import docs_path, render_tools_table


def test_docs_in_sync() -> None:
    expected = render_tools_table()
    actual = docs_path().read_text(encoding="utf-8")
    assert actual == expected, (
        "docs/tools/README.md 已过期;运行 `uv run python -m contracts.docgen` 重新生成"
    )
