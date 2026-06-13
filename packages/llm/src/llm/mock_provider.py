"""MockProvider:回放预设的"思考 + 工具调用"序列,用于全部自动化测试。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

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
    ToolUseBlock,
    Usage,
)


@dataclass
class ScriptedTurn:
    """一轮预设回复:文本 + 0..n 个工具调用 + 停止原因。"""

    text: str = ""
    tool_calls: list[ToolUseBlock] = field(default_factory=list)
    stop_reason: str = "end_turn"


class MockProvider:
    """按 turn 索引回放剧本;complete 与 stream 共享同一进度。"""

    def __init__(self, turns: Sequence[ScriptedTurn], *, chunk_size: int = 8) -> None:
        self._turns: list[ScriptedTurn] = list(turns)
        self._index = 0
        self._chunk_size = chunk_size

    def _next_turn(self) -> ScriptedTurn:
        if self._index >= len(self._turns):
            return ScriptedTurn(text="(mock: 剧本已结束)")  # 兜底,避免循环卡死
        turn = self._turns[self._index]
        self._index += 1
        return turn

    @staticmethod
    def _response(turn: ScriptedTurn) -> LlmResponse:
        raw: list[ContentBlock] = []
        if turn.text:
            raw.append(TextBlock(turn.text))
        raw.extend(turn.tool_calls)
        return LlmResponse(
            text=turn.text,
            tool_calls=list(turn.tool_calls),
            stop_reason=turn.stop_reason,
            usage=Usage(input_tokens=0, output_tokens=len(turn.text)),
            raw_content=raw,
        )

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> LlmResponse:
        return self._response(self._next_turn())

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        turn = self._next_turn()
        for i in range(0, len(turn.text), self._chunk_size):
            yield TextDelta(turn.text[i : i + self._chunk_size])
        for tc in turn.tool_calls:
            yield ToolCallStarted(tc)
        yield StreamDone(self._response(turn))
