"""自动生成工具索引文档 docs/tools/README.md(要求 9)。

`render_tools_table()` 是纯函数(可被测试断言不漂移);`write_docs()` 落盘;
`python -m contracts.docgen` 为重新生成的 CLI。
"""

from __future__ import annotations

from pathlib import Path

from .loader import load_toolspecs
from .paths import find_repo_root

_DOMAIN_ORDER: dict[str, int] = {"rag": 0, "data": 1, "code": 2, "sop": 3, "base": 4, "domain": 5}

_HEADER = (
    "<!-- AUTO-GENERATED:由 `uv run python -m contracts.docgen` 生成,请勿手工编辑。"
    "改动工具规格后重新生成(contract-test 会校验本文件未漂移)。 -->\n"
    "# 工具索引(自动生成)\n\n"
    "汇总 `contracts/toolspec/` 下全部工具规格(CLAUDE.md §5 / DoD §7 第 4 条)。\n\n"
)


def render_tools_table() -> str:
    rows = sorted(load_toolspecs(), key=lambda ls: (_DOMAIN_ORDER.get(ls.domain, 9), ls.spec.name))
    lines = [
        "| 工具 | 域 | side_effects | confirmation_required | enabled_by_default |",
        "|------|----|--------------|-----------------------|--------------------|",
    ]
    for ls in rows:
        s = ls.spec
        lines.append(
            f"| `{s.name}` | {ls.domain} | {s.side_effects.value} | "
            f"{str(s.confirmation_required).lower()} | {str(s.enabled_by_default).lower()} |"
        )
    return _HEADER + "\n".join(lines) + "\n"


def docs_path() -> Path:
    return find_repo_root() / "docs" / "tools" / "README.md"


def write_docs() -> Path:
    out = docs_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_tools_table(), encoding="utf-8")
    return out


def main() -> None:
    out = write_docs()
    print(f"已生成 {out}")


if __name__ == "__main__":
    main()
