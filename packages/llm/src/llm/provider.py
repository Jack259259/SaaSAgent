"""Provider 接口(complete / stream,支持 tool-calls 协议)。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, runtime_checkable

from .types import LlmResponse, Message, StreamEvent, ToolDef


class NotConfiguredError(RuntimeError):
    """LLM 未配置(缺 LLM_API_KEY 等);映射到 ToolSpec 错误 NOT_CONFIGURED。"""


@runtime_checkable
class Provider(Protocol):
    """LLM 后端统一接口。实现:AnthropicProvider(真实)、MockProvider(测试)。"""

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> LlmResponse: ...

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]: ...
