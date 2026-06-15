"""AnthropicProvider:真实 Anthropic 后端(读 env;未配置返回 NOT_CONFIGURED)。

依据 claude-api 技能:`AsyncAnthropic`、tool-use(tools / tool_use / tool_result)、
`messages.stream()`、prompt-cache(system 末块挂 cache_control)。默认模型 claude-opus-4-8
(env LLM_MODEL 覆盖)。**本阶段不被任何自动化测试触达**(测试用 MockProvider);
SDK 边界用 Any 承载,以避免与厂商联合类型纠缠,公开方法仍全类型化。
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Sequence
from typing import Any, cast

from .provider import NotConfiguredError
from .retry import RetryConfig, with_retry
from .tracing import current_trace_id, tracer
from .types import (
    ContentBlock,
    LlmResponse,
    Message,
    StreamDone,
    StreamEvent,
    TextBlock,
    TextDelta,
    ToolCallStarted,
    ToolDef,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
)

_DEFAULT_MODEL = "claude-opus-4-8"


class AnthropicProvider:
    def __init__(
        self,
        *,
        model: str | None = None,
        retry: RetryConfig | None = None,
        cache_system: bool = True,
    ) -> None:
        self._api_key = os.environ.get("LLM_API_KEY") or None
        self._model = model or os.environ.get("LLM_MODEL") or _DEFAULT_MODEL
        self._retry = retry or RetryConfig()
        self._cache_system = cache_system
        self._client: Any = None  # lazy

    def _ensure_client(self) -> Any:
        if not self._api_key:
            raise NotConfiguredError("LLM_API_KEY 未配置")
        if self._client is None:
            import anthropic  # lazy:仅在真正调用时依赖 SDK

            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    def _system_param(self, system: str) -> list[dict[str, Any]]:
        block: dict[str, Any] = {"type": "text", "text": system}
        if self._cache_system:
            block["cache_control"] = {"type": "ephemeral"}  # prompt-cache 钩子
        return [block]

    @staticmethod
    def _to_api_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            content: list[dict[str, Any]] = []
            for b in m.content:
                if isinstance(b, TextBlock):
                    content.append({"type": "text", "text": b.text})
                elif isinstance(b, ToolUseBlock):
                    content.append(
                        {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                    )
                elif isinstance(b, ToolResultBlock):
                    content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": b.tool_use_id,
                            "content": b.content,
                            "is_error": b.is_error,
                        }
                    )
            out.append({"role": m.role.value, "content": content})
        return out

    @staticmethod
    def _to_api_tools(tools: Sequence[ToolDef]) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]

    @staticmethod
    def _parse_content(blocks: Any) -> tuple[str, list[ToolUseBlock], list[ContentBlock]]:
        text_parts: list[str] = []
        tool_calls: list[ToolUseBlock] = []
        raw: list[ContentBlock] = []
        for block in blocks:
            btype = getattr(block, "type", None)
            if btype == "text":
                text = cast(str, block.text)
                text_parts.append(text)
                raw.append(TextBlock(text))
            elif btype == "tool_use":
                tc = ToolUseBlock(
                    id=cast(str, block.id),
                    name=cast(str, block.name),
                    input=cast("dict[str, Any]", block.input),
                )
                tool_calls.append(tc)
                raw.append(tc)
        return "".join(text_parts), tool_calls, raw

    @staticmethod
    def _usage(raw_usage: Any) -> Usage:
        return Usage(
            input_tokens=int(getattr(raw_usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(raw_usage, "output_tokens", 0) or 0),
        )

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> LlmResponse:
        client = self._ensure_client()

        async def _call() -> Any:
            return await client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=self._system_param(system),
                tools=self._to_api_tools(tools),
                messages=self._to_api_messages(messages),
            )

        with tracer().span("llm.complete", trace_id=current_trace_id()):
            resp = await with_retry(_call, self._retry)
        text, tool_calls, raw = self._parse_content(resp.content)
        return LlmResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=str(resp.stop_reason or "end_turn"),
            usage=self._usage(resp.usage),
            raw_content=raw,
        )

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        client = self._ensure_client()
        with tracer().span("llm.stream", trace_id=current_trace_id()):
            async with client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                system=self._system_param(system),
                tools=self._to_api_tools(tools),
                messages=self._to_api_messages(messages),
            ) as stream:
                async for text in stream.text_stream:
                    yield TextDelta(cast(str, text))
                final = await stream.get_final_message()
            text, tool_calls, raw = self._parse_content(final.content)
            for tc in tool_calls:
                yield ToolCallStarted(tc)
            yield StreamDone(
                LlmResponse(
                    text=text,
                    tool_calls=tool_calls,
                    stop_reason=str(final.stop_reason or "end_turn"),
                    usage=self._usage(final.usage),
                    raw_content=raw,
                )
            )
