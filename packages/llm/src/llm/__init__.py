"""llm —— LLM 网关(方案 §11.4)。

Provider 接口 + AnthropicProvider(真实)/ MockProvider(测试)+ 统一重试 / 超时。
"""

from __future__ import annotations

from .anthropic_provider import AnthropicProvider
from .embedding import Embedder, HashingEmbedder
from .mock_provider import MockProvider, ScriptedTurn
from .provider import NotConfiguredError, Provider
from .retry import RetryConfig, with_retry
from .types import (
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
    assistant_message,
    tool_results_message,
)

__version__ = "0.1.0"

__all__ = [
    "AnthropicProvider",
    "Embedder",
    "HashingEmbedder",
    "LlmResponse",
    "Message",
    "MockProvider",
    "NotConfiguredError",
    "Provider",
    "RetryConfig",
    "Role",
    "ScriptedTurn",
    "StreamDone",
    "StreamEvent",
    "TextBlock",
    "TextDelta",
    "ToolCallStarted",
    "ToolDef",
    "ToolResultBlock",
    "ToolUseBlock",
    "Usage",
    "assistant_message",
    "tool_results_message",
    "with_retry",
]
