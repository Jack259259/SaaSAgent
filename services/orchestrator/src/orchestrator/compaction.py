"""滚动压缩(§4.3)。阶段 2 先用截断策略并留接口,后续可换摘要式压缩。"""

from __future__ import annotations

from typing import Protocol

from llm import Message, ToolResultBlock


def _has_tool_result(message: Message) -> bool:
    """该消息是否含 tool_result 块(用于判定截断边界的孤儿)。"""
    return any(isinstance(b, ToolResultBlock) for b in message.content)


class Compactor(Protocol):
    def compact(self, messages: list[Message]) -> list[Message]: ...


class TruncationCompactor:
    """超过上限时保留首条(用户原始诉求)+ 最近若干轮,丢弃中间历史。"""

    def __init__(self, max_messages: int = 40) -> None:
        self._max = max_messages

    def compact(self, messages: list[Message]) -> list[Message]:
        if len(messages) <= self._max:
            return messages
        keep_tail = self._max - 1
        if keep_tail <= 0:
            return messages[:1]  # 退化配置(max≤1):仅留首条;规避 messages[-0:]==整列 的陷阱
        tail = messages[len(messages) - keep_tail :]
        # 截断边界可能切在 tool_use / tool_result 之间:丢弃开头的孤儿 tool_result
        # (其配对 assistant tool_use 已被裁),否则发往 LLM 会因 tool_result 无前驱而报错。
        while tail and _has_tool_result(tail[0]):
            tail = tail[1:]
        return [messages[0], *tail]
