"""Plan&Execute 集成测试(§4.1/§4.5):计划→并行步骤→一步失败→replan→完成;写步骤确认暂停→恢复。

用路由式 MockProvider(按当前轮的最后一条消息选回复),并发执行下保持确定。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from contracts import ToolSpec, UserCtx
from contracts.models import ErrorCode, SideEffect
from llm import Message, MockProvider, Role, ScriptedTurn, TextBlock, ToolUseBlock
from orchestrator import (
    AnswerDeltaEvent,
    ConfirmRequestEvent,
    DoneEvent,
    Orchestrator,
    PlanEvent,
    Session,
    ToolCallEvent,
    ToolContext,
    ToolOutcome,
    ToolRegistry,
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


def _user_ctx() -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=["*"]
    )


async def _echo(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    return ToolOutcome(summary=f"echoed: {args.get('text', '')}", raw={"echoed": args.get("text")})


async def _fail(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    raise RuntimeError("boom")


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(_spec("echo_tool", "test.echo"), _echo)
    reg.register(_spec("fail_tool", "test.fail"), _fail)
    return reg


def _last_text(messages: Sequence[Message]) -> str:
    if not messages:
        return ""
    return " ".join(b.text for b in messages[-1].content if isinstance(b, TextBlock))


def _update_plan(call_id: str, steps: list[dict[str, Any]]) -> ScriptedTurn:
    return ScriptedTurn(
        tool_calls=[ToolUseBlock(id=call_id, name="update_plan", input={"steps": steps})],
        stop_reason="tool_use",
    )


def _new_session() -> Session:
    s = Session(session_id="s-test", trace_id="t-1", user_ctx=_user_ctx())
    s.messages.append(Message(role=Role.user, content=[TextBlock("诊断:报表对不上")]))
    return s


async def test_plan_parallel_fail_replan_complete() -> None:
    def router(messages: Sequence[Message]) -> ScriptedTurn:
        last = _last_text(messages)
        if "请综合" in last:
            return ScriptedTurn(text="综合结论:已定位差异", stop_reason="end_turn")
        if "上一步校验未通过" in last:
            return ScriptedTurn(
                tool_calls=[ToolUseBlock(id="f", name="fail_tool", input={})],
                stop_reason="tool_use",
            )
        if "步骤失败" in last:
            return _update_plan(
                "p1", [{"id": "s1", "goal": "取数"}, {"id": "s3", "goal": "查知识(改用 echo)"}]
            )
        if "执行步骤 s1" in last:
            return ScriptedTurn(
                tool_calls=[ToolUseBlock(id="e1", name="echo_tool", input={"text": "s1"})],
                stop_reason="tool_use",
            )
        if "执行步骤 s2" in last:
            return ScriptedTurn(
                tool_calls=[ToolUseBlock(id="f2", name="fail_tool", input={})],
                stop_reason="tool_use",
            )
        if "执行步骤 s3" in last:
            return ScriptedTurn(
                tool_calls=[ToolUseBlock(id="e3", name="echo_tool", input={"text": "s3"})],
                stop_reason="tool_use",
            )
        # 规划轮:两个无依赖步骤
        return _update_plan("p0", [{"id": "s1", "goal": "取数"}, {"id": "s2", "goal": "查知识"}])

    orch = Orchestrator(provider=MockProvider(router=router), registry=_registry())
    session = _new_session()
    events = [e async for e in orch.advance(session)]

    plans = [e for e in events if isinstance(e, PlanEvent)]
    assert [p.version for p in plans] == [0, 1]  # 初始计划 + replan 各一次
    tools_called = {e.tool for e in events if isinstance(e, ToolCallEvent)}
    assert {"echo_tool", "fail_tool"} <= tools_called  # 两无依赖步骤都执行了(并行)
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done[-1].stop_reason == "completed"
    answer = "".join(e.text for e in events if isinstance(e, AnswerDeltaEvent))
    assert "综合结论" in answer
    assert session.replan_count == 1


async def test_confirm_pause_and_resume() -> None:
    def router(messages: Sequence[Message]) -> ScriptedTurn:
        last = _last_text(messages)
        if "请综合" in last:
            return ScriptedTurn(text="已完成写操作", stop_reason="end_turn")
        if "执行步骤 w1" in last:
            return ScriptedTurn(
                tool_calls=[ToolUseBlock(id="e", name="echo_tool", input={"text": "write"})],
                stop_reason="tool_use",
            )
        return _update_plan(
            "p0", [{"id": "w1", "goal": "提交计划(写)", "needs_confirmation": True}]
        )

    orch = Orchestrator(provider=MockProvider(router=router), registry=_registry())
    session = _new_session()

    seg1 = [e async for e in orch.advance(session)]
    confirms = [e for e in seg1 if isinstance(e, ConfirmRequestEvent)]
    assert len(confirms) == 1
    assert confirms[0].id == "w1"
    assert session.pending is not None and session.pending.kind == "confirm"
    # 段1 不应已完成
    assert not any(isinstance(e, DoneEvent) for e in seg1)

    seg2 = [e async for e in orch.resume(session, confirmation={"confirmed": True})]
    assert any(isinstance(e, ToolCallEvent) and e.tool == "echo_tool" for e in seg2)
    done = [e for e in seg2 if isinstance(e, DoneEvent)]
    assert done[-1].stop_reason == "completed"
    assert session.pending is None
