"""ReAct 主循环(§11.2):调工具再作答、越权拒绝、预算/防打转停止。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from structlog.testing import capture_logs

from contracts import ToolSpec, UserCtx
from contracts.models import ErrorCode, SideEffect
from llm import MockProvider, ScriptedTurn, ToolUseBlock
from orchestrator import (
    AnswerDeltaEvent,
    Budget,
    DoneEvent,
    Orchestrator,
    StepEvent,
    ToolCallEvent,
    ToolOutcome,
    ToolRegistry,
    ToolResultSummaryEvent,
)


def _spec(name: str, scope: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"{name}(测试)",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        output_schema={"type": "object"},
        permission_scope=scope,
        side_effects=SideEffect.read,
        confirmation_required=False,
        timeout_ms=5000,
        errors=[ErrorCode.VALIDATION_FAILED],
    )


def _user_ctx(perms: Sequence[str] = ("*",)) -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=list(perms)
    )


async def _echo_handler(args: dict[str, Any], user_ctx: UserCtx) -> ToolOutcome:
    text = str(args.get("text", ""))
    return ToolOutcome(summary=f"echoed: {text}", raw={"echoed": text})


async def _fail_handler(args: dict[str, Any], user_ctx: UserCtx) -> ToolOutcome:
    raise RuntimeError("boom")


def _echo_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(_spec("echo_tool", "test.echo"), _echo_handler)
    return reg


async def test_react_tool_then_answer() -> None:
    provider = MockProvider(
        [
            ScriptedTurn(
                text="我来回显一下",
                tool_calls=[ToolUseBlock(id="c1", name="echo_tool", input={"text": "hi"})],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text="回显结果是 hi", stop_reason="end_turn"),
        ]
    )
    orch = Orchestrator(provider=provider, registry=_echo_registry())
    events = [
        e async for e in orch.run(user_ctx=_user_ctx(), user_message="回显 hi", trace_id="t-1")
    ]
    names = [type(e).__name__ for e in events]

    assert any(isinstance(e, StepEvent) for e in events)
    tool_calls = [e for e in events if isinstance(e, ToolCallEvent)]
    assert tool_calls[0].tool == "echo_tool"
    summaries = [e for e in events if isinstance(e, ToolResultSummaryEvent)]
    assert summaries[0].summary == "echoed: hi"
    assert summaries[0].workspace_ref.startswith("ws://")
    answer = "".join(e.text for e in events if isinstance(e, AnswerDeltaEvent))
    assert answer == "回显结果是 hi"
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done[-1].stop_reason == "end_turn"
    # 事件顺序:tool_call → tool_result_summary → answer_delta
    assert (
        names.index("ToolCallEvent")
        < names.index("ToolResultSummaryEvent")
        < names.index("AnswerDeltaEvent")
    )


async def test_no_permission_tool_denied_and_audited() -> None:
    provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="c1", name="echo_tool", input={"text": "x"})],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text="完成", stop_reason="end_turn"),
        ]
    )
    orch = Orchestrator(provider=provider, registry=_echo_registry())
    with capture_logs() as logs:
        events = [
            e
            async for e in orch.run(user_ctx=_user_ctx(perms=[]), user_message="x", trace_id="t-2")
        ]
    summaries = [e for e in events if isinstance(e, ToolResultSummaryEvent)]
    assert summaries[0].summary == "无权限调用该工具"
    assert any(entry.get("result_status") == "denied" for entry in logs)


async def test_budget_exhausted_returns_partial() -> None:
    provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="c1", name="echo_tool", input={"text": "a"})],
                stop_reason="tool_use",
            ),
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="c2", name="echo_tool", input={"text": "b"})],
                stop_reason="tool_use",
            ),
        ]
    )
    orch = Orchestrator(
        provider=provider, registry=_echo_registry(), budget=Budget(max_steps=2, max_cost=100.0)
    )
    events = [e async for e in orch.run(user_ctx=_user_ctx(), user_message="loop", trace_id="t-3")]
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done[-1].stop_reason == "budget_exhausted"


async def test_no_progress_stops() -> None:
    reg = ToolRegistry()
    reg.register(_spec("fail_tool", "test.fail"), _fail_handler)
    provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="c1", name="fail_tool", input={})],
                stop_reason="tool_use",
            ),
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="c2", name="fail_tool", input={})],
                stop_reason="tool_use",
            ),
        ]
    )
    orch = Orchestrator(provider=provider, registry=reg, no_progress_limit=2)
    events = [e async for e in orch.run(user_ctx=_user_ctx(), user_message="x", trace_id="t-4")]
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done[-1].stop_reason == "no_progress"
