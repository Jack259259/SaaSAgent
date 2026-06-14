"""会话与会话存储(支撑跨请求的暂停/恢复)。

Plan&Execute 中的写步骤确认(红线 4)与 ask_user 澄清都需跨请求恢复:`/chat` 段在暂停点
结束本段流并保存会话,`/chat/confirm` 段载入会话继续。会话按 tenant/user 隔离(红线 3/9)。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from contracts import UserCtx
from contracts.models import Plan
from llm import Message

from .workspace import Workspace


class SessionNotFoundError(Exception):
    """会话不存在。"""


class SessionAccessError(Exception):
    """跨租户 / 跨用户访问会话(红线 9);映射到 403。"""


@dataclass
class Pending:
    """当前等待的用户交互(暂停点)。"""

    kind: str  # "confirm" | "ask_user" | "tool_confirm"
    step_id: str | None = None
    tool_use_id: str | None = None
    questions: list[dict[str, Any]] | None = None
    tool_name: str | None = None  # tool_confirm:待续行的工具名
    confirm_token: str | None = None  # tool_confirm:续行令牌(如 SOP run_id)


@dataclass
class Session:
    session_id: str
    trace_id: str
    user_ctx: UserCtx
    messages: list[Message] = field(default_factory=list)
    workspace: Workspace = field(default_factory=Workspace)
    plan: Plan | None = None
    phase: str = "planning"  # planning | executing | finalizing | done
    mode: str = "react"  # react | plan_execute
    pending: Pending | None = None
    confirmed_step_ids: set[str] = field(default_factory=set)
    done_step_ids: set[str] = field(default_factory=set)
    verdicts: list[dict[str, Any]] = field(default_factory=list)
    used_steps: int = 0
    used_cost: float = 0.0
    used_tokens: int = 0
    replan_count: int = 0
    page_context: dict[str, Any] | None = None


class SessionStore:
    """进程内会话存储(阶段 3 内存版;后续阶段可换持久化)。按 tenant/user 隔离。"""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(
        self,
        *,
        user_ctx: UserCtx,
        trace_id: str,
        page_context: dict[str, Any] | None = None,
    ) -> Session:
        session_id = uuid.uuid4().hex
        session = Session(
            session_id=session_id,
            trace_id=trace_id,
            user_ctx=user_ctx,
            page_context=page_context,
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str, user_ctx: UserCtx) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        # 红线 3/9:跨租户、跨用户绝不互见。
        if (
            session.user_ctx.tenant_id != user_ctx.tenant_id
            or session.user_ctx.user_id != user_ctx.user_id
        ):
            raise SessionAccessError(session_id)
        return session
