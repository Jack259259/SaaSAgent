"""Provider 无关的 LLM 类型层(阶段 2)。

不外泄任何厂商(anthropic)类型——MockProvider 与 AnthropicProvider 共用这套类型,
是"框架无关接缝"的一部分(CLAUDE.md 红线 5)。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    system = "system"
    user = "user"
    assistant = "assistant"


@dataclass(frozen=True)
class TextBlock:
    text: str


@dataclass(frozen=True)
class ToolUseBlock:
    """模型请求调用某工具。"""

    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResultBlock:
    """工具执行结果回传(作为 user 消息内容块)。"""

    tool_use_id: str
    content: str
    is_error: bool = False


ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock


@dataclass
class Message:
    role: Role
    content: list[ContentBlock]


@dataclass(frozen=True)
class ToolDef:
    """传给 Provider 的工具定义(name/description/input_schema)。"""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class LlmResponse:
    text: str
    tool_calls: list[ToolUseBlock]
    stop_reason: str
    usage: Usage
    raw_content: list[ContentBlock]


# ---- 流式事件 ---------------------------------------------------------------
@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCallStarted:
    tool_call: ToolUseBlock


@dataclass(frozen=True)
class StreamDone:
    response: LlmResponse


StreamEvent = TextDelta | ToolCallStarted | StreamDone


def assistant_message(response: LlmResponse) -> Message:
    """把一次 LLM 回复重建为可回传的 assistant 消息(含 text + tool_use 块)。"""
    return Message(role=Role.assistant, content=list(response.raw_content))


def tool_results_message(results: list[ToolResultBlock]) -> Message:
    """把若干工具结果打包为一条 user 消息(Anthropic 约定 tool_result 走 user 角色)。"""
    content: list[ContentBlock] = list(results)
    return Message(role=Role.user, content=content)
