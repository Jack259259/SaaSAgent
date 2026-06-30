"""OpenAIProvider:真实 OpenAI 兼容后端(/v1/chat/completions;未配置返回 NOT_CONFIGURED)。

与 AnthropicProvider 同实现 `Provider` Protocol(complete / stream / tool-calls),上层 orchestrator
不感知底层格式(types.py 厂商无关接缝)。用官方 `openai` SDK 的 `AsyncOpenAI`:鉴权头
(Authorization: Bearer)由 SDK 负责。默认模型 `gpt-4o-mini`(env LLM_MODEL / 配置 model 覆盖)。
**本阶段不被任何自动化测试触网**(测试用 MockProvider + 不触网的转换/解析单测);SDK 边界用 Any
承载以避免与厂商联合类型纠缠,公开方法仍全类型化。

关键格式差异(对 Anthropic):system 放进 messages 数组、tool_result 各拆成独立 `role:"tool"` 消息、
工具定义用 `function.parameters`、响应读 `choices[0].message` + `finish_reason`、流式按 index 累积
`delta.content` / `delta.tool_calls`。
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Sequence
from typing import Any

from .provider import NotConfiguredError
from .retry import RetryConfig, with_retry
from .tracing import current_trace_id, tracer
from .types import (
    ContentBlock,
    LlmResponse,
    Message,
    Role,
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

_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider:
    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        retry: RetryConfig | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("LLM_API_KEY") or None
        self._model = model or os.environ.get("LLM_MODEL") or _DEFAULT_MODEL
        self._base_url = (
            base_url or os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or None
        )
        self._retry = retry or RetryConfig()
        self._client: Any = None  # lazy

    def _ensure_client(self) -> Any:
        if not self._api_key:
            raise NotConfiguredError("LLM api_key 未配置(config/llm.yml 或 LLM_API_KEY)")
        if self._client is None:
            import openai  # lazy:仅在真正调用时依赖 SDK

            kwargs: dict[str, Any] = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = openai.AsyncOpenAI(**kwargs)
        return self._client

    @staticmethod
    def _api_messages_with_system(system: str, messages: Sequence[Message]) -> list[dict[str, Any]]:
        """OpenAI 把 system 放进 messages 数组首条(Anthropic 是独立参数)。"""
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        out.extend(OpenAIProvider._to_api_messages(messages))
        return out

    @staticmethod
    def _to_api_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
        """厂商无关 Message → OpenAI chat 消息;一条可能映射为多条(tool_result 各成独立消息)。"""
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == Role.assistant:
                text_parts: list[str] = []
                tool_calls: list[dict[str, Any]] = []
                for b in m.content:
                    if isinstance(b, TextBlock):
                        text_parts.append(b.text)
                    elif isinstance(b, ToolUseBlock):
                        tool_calls.append(
                            {
                                "id": b.id,
                                "type": "function",
                                "function": {
                                    "name": b.name,
                                    "arguments": json.dumps(b.input, ensure_ascii=False),
                                },
                            }
                        )
                # OpenAI:assistant 消息需 content 或 tool_calls 至少其一;无文本时 content=None。
                msg: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts) or None}
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                out.append(msg)
            elif m.role == Role.system:
                text = "".join(b.text for b in m.content if isinstance(b, TextBlock))
                out.append({"role": "system", "content": text})
            else:  # user:tool_result 各拆为 role:"tool" 消息,文本聚为一条 user 消息
                user_text: list[str] = []
                for b in m.content:
                    if isinstance(b, ToolResultBlock):
                        out.append(
                            {
                                "role": "tool",
                                "tool_call_id": b.tool_use_id,
                                "content": b.content,
                            }
                        )
                    elif isinstance(b, TextBlock):
                        user_text.append(b.text)
                if user_text:
                    out.append({"role": "user", "content": "".join(user_text)})
        return out

    @staticmethod
    def _to_api_tools(tools: Sequence[ToolDef]) -> list[dict[str, Any]]:
        """ToolDef → OpenAI function 工具(function.parameters ↔ Anthropic 的 input_schema)。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

    @staticmethod
    def _parse_tool_args(arguments: Any) -> dict[str, Any]:
        if not arguments:
            return {}
        try:
            parsed = json.loads(arguments)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @classmethod
    def _parse_message(cls, message: Any) -> tuple[str, list[ToolUseBlock], list[ContentBlock]]:
        text_parts: list[str] = []
        tool_calls: list[ToolUseBlock] = []
        raw: list[ContentBlock] = []
        content = getattr(message, "content", None)
        if content:
            text_parts.append(str(content))
            raw.append(TextBlock(str(content)))
        for tc in getattr(message, "tool_calls", None) or []:
            fn = getattr(tc, "function", None)
            block = ToolUseBlock(
                id=str(getattr(tc, "id", "") or ""),
                name=str(getattr(fn, "name", "") or ""),
                input=cls._parse_tool_args(getattr(fn, "arguments", None)),
            )
            tool_calls.append(block)
            raw.append(block)
        return "".join(text_parts), tool_calls, raw

    @staticmethod
    def _usage(raw_usage: Any) -> Usage:
        return Usage(
            input_tokens=int(getattr(raw_usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(raw_usage, "completion_tokens", 0) or 0),
        )

    def _create_kwargs(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef],
        max_tokens: int,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": self._api_messages_with_system(system, messages),
        }
        api_tools = self._to_api_tools(tools)
        if api_tools:  # 省略空 tools,兼容更严格的网关
            kwargs["tools"] = api_tools
        return kwargs

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> LlmResponse:
        client = self._ensure_client()
        kwargs = self._create_kwargs(
            system=system, messages=messages, tools=tools, max_tokens=max_tokens
        )

        async def _call() -> Any:
            return await client.chat.completions.create(**kwargs)

        with tracer().span("llm.complete", trace_id=current_trace_id()):
            resp = await with_retry(_call, self._retry)
        choice = resp.choices[0]
        text, tool_calls, raw = self._parse_message(choice.message)
        return LlmResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=str(getattr(choice, "finish_reason", None) or "stop"),
            usage=self._usage(getattr(resp, "usage", None)),
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
        kwargs = self._create_kwargs(
            system=system, messages=messages, tools=tools, max_tokens=max_tokens
        )
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}  # 末块带 usage(兼容端点可忽略)

        with tracer().span("llm.stream", trace_id=current_trace_id()):
            text_parts: list[str] = []
            frags: dict[int, dict[str, str]] = {}  # index -> {id,name,args}
            order: list[int] = []
            finish_reason: str | None = None
            usage_raw: Any = None

            stream = await client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage_raw = chunk.usage
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                choice = choices[0]
                delta = getattr(choice, "delta", None)
                content = getattr(delta, "content", None)
                if content:
                    text_parts.append(str(content))
                    yield TextDelta(str(content))
                for tcd in getattr(delta, "tool_calls", None) or []:
                    idx = int(getattr(tcd, "index", 0) or 0)
                    slot = frags.get(idx)
                    if slot is None:
                        slot = {"id": "", "name": "", "args": ""}
                        frags[idx] = slot
                        order.append(idx)
                    tc_id = getattr(tcd, "id", None)
                    if tc_id:
                        slot["id"] = str(tc_id)
                    fn = getattr(tcd, "function", None)
                    if fn is not None:
                        name = getattr(fn, "name", None)
                        if name:
                            slot["name"] = str(name)
                        args = getattr(fn, "arguments", None)
                        if args:
                            slot["args"] += str(args)
                if getattr(choice, "finish_reason", None):
                    finish_reason = str(choice.finish_reason)

            tool_calls: list[ToolUseBlock] = []
            raw: list[ContentBlock] = []
            full_text = "".join(text_parts)
            if full_text:
                raw.append(TextBlock(full_text))
            for idx in order:
                slot = frags[idx]
                block = ToolUseBlock(
                    id=slot["id"], name=slot["name"], input=self._parse_tool_args(slot["args"])
                )
                tool_calls.append(block)
                raw.append(block)
            for tc in tool_calls:
                yield ToolCallStarted(tc)
            yield StreamDone(
                LlmResponse(
                    text=full_text,
                    tool_calls=tool_calls,
                    stop_reason=finish_reason or "stop",
                    usage=self._usage(usage_raw),
                    raw_content=raw,
                )
            )
