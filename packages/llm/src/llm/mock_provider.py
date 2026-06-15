"""MockProvider:回放预设的"思考 + 工具调用"序列,用于全部自动化测试。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field

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
    ToolUseBlock,
    Usage,
)


@dataclass
class ScriptedTurn:
    """一轮预设回复:文本 + 0..n 个工具调用 + 停止原因。"""

    text: str = ""
    tool_calls: list[ToolUseBlock] = field(default_factory=list)
    stop_reason: str = "end_turn"


# 内容路由:按当前消息决定下一轮回复(并发执行下保持确定,阶段 3 Plan&Execute 需要)。
TurnRouter = Callable[[Sequence[Message]], ScriptedTurn]


class MockProvider:
    """回放预设剧本。两种模式:

    - 索引模式(默认):按 turn 顺序回放,complete 与 stream 共享进度(阶段 2 用法)。
    - 路由模式:传 router(messages)->ScriptedTurn,按消息内容选回复,并发下确定(阶段 3 用法)。
    """

    def __init__(
        self,
        turns: Sequence[ScriptedTurn] | None = None,
        *,
        router: TurnRouter | None = None,
        chunk_size: int = 8,
    ) -> None:
        self._turns: list[ScriptedTurn] = list(turns or [])
        self._router = router
        self._index = 0
        self._chunk_size = chunk_size

    def _pick_turn(self, messages: Sequence[Message]) -> ScriptedTurn:
        if self._router is not None:
            return self._router(messages)
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
        with tracer().span("llm.complete", trace_id=current_trace_id()):
            return self._response(self._pick_turn(messages))

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        with tracer().span("llm.stream", trace_id=current_trace_id()):
            turn = self._pick_turn(messages)
            for i in range(0, len(turn.text), self._chunk_size):
                yield TextDelta(turn.text[i : i + self._chunk_size])
            for tc in turn.tool_calls:
                yield ToolCallStarted(tc)
            yield StreamDone(self._response(turn))
