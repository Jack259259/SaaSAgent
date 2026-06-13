"""工具注册表(红线 2:能力只经契约暴露;红线 3:调用前二次校验)。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from contracts import ToolSpec
from contracts.loader import load_toolspecs
from contracts.models import ErrorCode
from llm import ToolDef

from .permissions import DefaultPermissionChecker, PermissionChecker
from .tool_context import ToolContext


class ToolNotFoundError(Exception):
    """调用了未注册的工具;映射到 NOT_FOUND。"""

    code = ErrorCode.NOT_FOUND


@dataclass
class ToolOutcome:
    """工具执行结果:摘要进上下文,raw 落工作区(红线 8)。"""

    summary: str
    raw: Any = None
    is_error: bool = False


ToolHandler = Callable[[dict[str, Any], ToolContext], Awaitable[ToolOutcome]]


@dataclass
class _Entry:
    spec: ToolSpec
    handler: ToolHandler


class ToolRegistry:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._entries: dict[str, _Entry] = {}
        self._checker: PermissionChecker = checker or DefaultPermissionChecker()

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        self._entries[spec.name] = _Entry(spec=spec, handler=handler)

    def register_from_contracts(self, handlers: dict[str, ToolHandler]) -> None:
        """从 contracts/toolspec 加载规格并绑定 handler(仅登记提供了 handler 的工具)。"""
        by_name = {ls.spec.name: ls.spec for ls in load_toolspecs()}
        for name, handler in handlers.items():
            spec = by_name.get(name)
            if spec is None:
                raise ToolNotFoundError(f"契约中无此工具:{name}")
            self.register(spec, handler)

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
        return await entry.handler(arguments, ctx)
