"""滚动压缩(§4.3)。阶段 2 先用截断策略并留接口,后续可换摘要式压缩。"""

from __future__ import annotations

from typing import Protocol

from llm import Message


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
        return [messages[0], *messages[-keep_tail:]]
