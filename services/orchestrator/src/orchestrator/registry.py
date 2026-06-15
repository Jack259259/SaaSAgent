"""工具注册表(红线 2:能力只经契约暴露;红线 3:调用前二次校验)。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from contracts import ToolSpec
from contracts.loader import load_toolspecs
from contracts.models import ErrorCode
from llm import ToolDef, Tracer, get_tracer

from .permissions import DefaultPermissionChecker, PermissionChecker
from .tool_context import ToolContext


class ToolNotFoundError(Exception):
    """调用了未注册的工具;映射到 NOT_FOUND。"""

    code = ErrorCode.NOT_FOUND


@dataclass
class ToolConfirmation:
    """工具执行中途请求用户确认(如 run_sop 命中 confirm 步)。token 用于恢复(红线 4)。"""

    token: str
    prompt: str


@dataclass
class ToolOutcome:
    """工具执行结果:摘要进上下文,raw 落工作区(红线 8)。

    confirmation 置位表示工具已暂停、等待用户确认(编排器据此发 confirm_request 并暂停)。
    """

    summary: str
    raw: Any = None
    is_error: bool = False
    confirmation: ToolConfirmation | None = None


ToolHandler = Callable[[dict[str, Any], ToolContext], Awaitable[ToolOutcome]]
# 续行处理器:(token, confirmed, ctx) → 续跑后的结果(双闸第二闸在 handler/executor 内复验)。
ResumeHandler = Callable[[str, bool, ToolContext], Awaitable[ToolOutcome]]


@dataclass
class _Entry:
    spec: ToolSpec
    handler: ToolHandler
    resume: ResumeHandler | None = None


class ToolRegistry:
    def __init__(
        self, checker: PermissionChecker | None = None, *, tracer: Tracer | None = None
    ) -> None:
        self._entries: dict[str, _Entry] = {}
        self._checker: PermissionChecker = checker or DefaultPermissionChecker()
        self._tracer: Tracer = tracer or get_tracer()

    def register(
        self, spec: ToolSpec, handler: ToolHandler, *, resume: ResumeHandler | None = None
    ) -> None:
        self._entries[spec.name] = _Entry(spec=spec, handler=handler, resume=resume)

    def register_from_contracts(
        self,
        handlers: dict[str, ToolHandler],
        *,
        resumes: dict[str, ResumeHandler] | None = None,
    ) -> None:
        """从 contracts/toolspec 加载规格并绑定 handler(仅登记提供了 handler 的工具)。

        resumes:为支持「工具确认-恢复」的工具(如 run_sop)提供续行处理器。
        """
        by_name = {ls.spec.name: ls.spec for ls in load_toolspecs()}
        for name, handler in handlers.items():
            spec = by_name.get(name)
            if spec is None:
                raise ToolNotFoundError(f"契约中无此工具:{name}")
            self.register(spec, handler, resume=(resumes or {}).get(name))

    async def resume_tool(
        self, name: str, token: str, confirmed: bool, ctx: ToolContext
    ) -> ToolOutcome:
        """确认回执后续跑某工具(红线 4 第二闸由该工具/执行器内部复验确认)。"""
        entry = self._entries.get(name)
        if entry is None or entry.resume is None:
            raise ToolNotFoundError(f"工具不支持确认恢复:{name}")
        return await entry.resume(token, confirmed, ctx)

    def has(self, name: str) -> bool:
        return name in self._entries

    def spec(self, name: str) -> ToolSpec:
        entry = self._entries.get(name)
        if entry is None:
            raise ToolNotFoundError(name)
        return entry.spec

    def specs(self) -> list[ToolSpec]:
        return [e.spec for e in self._entries.values()]

    def tool_defs(self) -> list[ToolDef]:
        return [
            ToolDef(
                name=e.spec.name, description=e.spec.description, input_schema=e.spec.input_schema
            )
            for e in self._entries.values()
        ]

    async def invoke(self, name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        entry = self._entries.get(name)
        if entry is None:
            raise ToolNotFoundError(name)
        # 红线 3:调用前二次校验 user_ctx 与 permission_scope,不通过抛 NoPermissionError。
        self._checker.check(ctx.user_ctx, entry.spec)
        # span 经 ctx.trace_id 串接(贯穿主 Agent / 子 Agent;红线 7:不记 raw 结果)。
        with self._tracer.span(f"tool.{name}", trace_id=ctx.trace_id, tool=name):
            return await entry.handler(arguments, ctx)
