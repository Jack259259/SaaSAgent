"""MockProvider 与 retry 的单测(阶段 2)。"""

from __future__ import annotations

import asyncio

import pytest

from llm import MockProvider, ScriptedTurn, ToolUseBlock
from llm.retry import RetryConfig, with_retry
from llm.types import StreamDone, TextDelta, ToolCallStarted


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
