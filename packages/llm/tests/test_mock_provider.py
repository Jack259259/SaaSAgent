"""MockProvider 与 retry 的单测(阶段 2)。"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest

from llm import Message, MockProvider, Role, ScriptedTurn, TextBlock, ToolUseBlock
from llm.retry import RetryConfig, with_retry
from llm.types import StreamDone, TextDelta, ToolCallStarted


async def test_router_mode_picks_by_content() -> None:
    def router(messages: Sequence[Message]) -> ScriptedTurn:
        last = " ".join(b.text for b in messages[-1].content if isinstance(b, TextBlock))
        return ScriptedTurn(text="A" if "alpha" in last else "B", stop_reason="end_turn")

    p = MockProvider(router=router)
    a = await p.complete(system="s", messages=[Message(Role.user, [TextBlock("alpha")])])
    b = await p.complete(system="s", messages=[Message(Role.user, [TextBlock("beta")])])
    assert a.text == "A"
    assert b.text == "B"  # 路由按内容,且不随调用次数漂移(并发确定)


async def test_complete_replays_turns() -> None:
    p = MockProvider([ScriptedTurn(text="hello", stop_reason="end_turn")])
    r = await p.complete(system="s", messages=[])
    assert r.text == "hello"
    assert r.stop_reason == "end_turn"
    assert r.tool_calls == []


async def test_stream_emits_deltas_then_tool_calls_then_done() -> None:
    tc = ToolUseBlock(id="c1", name="echo_tool", input={"text": "hi"})
    p = MockProvider(
        [ScriptedTurn(text="abcdefghij", tool_calls=[tc], stop_reason="tool_use")],
        chunk_size=4,
    )
    events = [e async for e in p.stream(system="s", messages=[])]
    deltas = [e for e in events if isinstance(e, TextDelta)]
    assert "".join(d.text for d in deltas) == "abcdefghij"
    assert any(isinstance(e, ToolCallStarted) for e in events)
    assert isinstance(events[-1], StreamDone)
    assert events[-1].response.tool_calls[0].name == "echo_tool"


async def test_with_retry_succeeds_after_failures() -> None:
    calls = {"n": 0}

    async def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"

    out = await with_retry(fn, RetryConfig(max_attempts=3, base_delay_s=0.0))
    assert out == "ok"
    assert calls["n"] == 3


async def test_with_retry_raises_after_max() -> None:
    async def fn() -> str:
        raise ValueError("always")

    with pytest.raises(ValueError, match="always"):
        await with_retry(fn, RetryConfig(max_attempts=2, base_delay_s=0.0))


async def test_with_retry_timeout() -> None:
    async def fn() -> str:
        await asyncio.sleep(1.0)
        return "x"

    with pytest.raises(asyncio.TimeoutError):
        await with_retry(fn, RetryConfig(max_attempts=1, timeout_s=0.05))
