"""基础工具 handler(§5.5)。"""

from __future__ import annotations

from sandbox_svc import SubprocessRunner

from ..registry import ToolHandler
from .analysis import make_run_analysis_handler
from .base import (
    export_file,
    get_page_context,
    parse_user_file,
    read_workspace,
    write_workspace,
)
from .knowledge import make_search_knowledge_handler


def base_tool_handlers() -> dict[str, ToolHandler]:
    """经注册表执行的基础工具(update_plan / ask_user 由循环拦截,不在此列)。

    run_analysis 用默认 SubprocessRunner(开发/CI 沙箱);生产应注入 ContainerRunner。
    """
    return {
        "get_page_context": get_page_context,
        "read_workspace": read_workspace,
        "write_workspace": write_workspace,
        "export_file": export_file,
        "parse_user_file": parse_user_file,
        "run_analysis": make_run_analysis_handler(SubprocessRunner()),
    }


__all__ = [
    "base_tool_handlers",
    "export_file",
    "get_page_context",
    "make_run_analysis_handler",
    "make_search_knowledge_handler",
    "parse_user_file",
    "read_workspace",
    "write_workspace",
]
