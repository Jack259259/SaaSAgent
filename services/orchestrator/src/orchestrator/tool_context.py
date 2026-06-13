"""工具执行上下文(随每次工具调用透传)。

携带 user_ctx(红线 3 二次校验依据)、会话工作区(读写句柄)、trace_id(审计)、
以及可选的 page_context(get_page_context 用,前端注入、按 user_ctx 过滤)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from contracts import UserCtx

from .workspace import Workspace


@dataclass
class ToolContext:
    user_ctx: UserCtx
    workspace: Workspace
    trace_id: str
    page_context: dict[str, Any] | None = None
