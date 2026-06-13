"""基础工具 handler(第一批,§5.5)。"""

from __future__ import annotations

from ..registry import ToolHandler
from .base import (
    export_file,
    get_page_context,
    parse_user_file,
    read_workspace,
    write_workspace,
)


def base_tool_handlers() -> dict[str, ToolHandler]:
    """经注册表执行的基础工具(update_plan / ask_user 由循环拦截,不在此列)。"""
    return {
        "get_page_context": get_page_context,
        "read_workspace": read_workspace,
        "write_workspace": write_workspace,
        "export_file": export_file,
        "parse_user_file": parse_user_file,
    }


__all__ = [
    "base_tool_handlers",
    "export_file",
    "get_page_context",
    "parse_user_file",
    "read_workspace",
    "write_workspace",
]
