"""行内反思(§4.1):默认 output_schema 校验器 + 失败回流重试 ≤2 + verdicts 留痕。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from contracts import ToolSpec, UserCtx
from contracts.models import ErrorCode, SideEffect
from llm import Message, MockProvider, Role, ScriptedTurn, TextBlock, ToolUseBlock
from orchestrator import (
    Orchestrator,
    Session,
    ToolContext,
    ToolOutcome,
    ToolRegistry,
    default_output_schema_verifier,
)

_BAD_SPEC = ToolSpec(
    name="bad_tool",
    description="产出缺字段(测试)",
    input_schema={"type": "object"},
    output_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["needed"],
        "properties": {"needed": {"type": "string"}},
    },
    permission_scope="test.bad",
    side_effects=SideEffect.read,
    confirmation_required=False,
    timeout_ms=5000,
    errors=[ErrorCode.VALIDATION_FAILED],
)


def test_verifier_pass_fail_error() -> None:
    ok = default_output_schema_verifier(ToolOutcome(summary="s", raw={"needed": "x"}), _BAD_SPEC)
    assert ok.ok is True
    bad = default_output_schema_verifier(ToolOutcome(summary="s", raw={"wrong": "x"}), _BAD_SPEC)
    assert bad.ok is False and "output_schema" in bad.critique
    err = default_output_schema_verifier(ToolOutcome(summary="boom", is_error=True), _BAD_SPEC)
    assert err.ok is False


async def test_step_retries_twice_then_fails() -> None:
    async def _bad(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        return ToolOutcome(summary="缺字段", raw={"wrong": "x"})  # 不符 output_schema

    reg = ToolRegistry()
    reg.register(_BAD_SPEC, _bad)

    def router(messages: Sequence[Message]) -> ScriptedTurn:
        last = " ".join(b.text for b in messages[-1].content if isinstance(b, TextBlock))
        if "请综合" in last:
            return ScriptedTurn(text="无法完成", stop_reason="end_turn")
        if "步骤失败" in last:
            return ScriptedTurn(text="无法修复,放弃重排", stop_reason="end_turn")  # replan 不改计划
        if "执行步骤 b1" in last or "上一步校验未通过" in last:
            return ScriptedTurn(
                tool_calls=[ToolUseBlock(id="b", name="bad_tool", input={})], stop_reason="tool_use"
            )
        return ScriptedTurn(
            tool_calls=[
                ToolUseBlock(
                    id="p", name="update_plan", input={"steps": [{"id": "b1", "goal": "产出"}]}
                )
            ],
            stop_reason="tool_use",
        )

    orch = Orchestrator(provider=MockProvider(router=router), registry=reg)
    session = Session(
        session_id="s",
        trace_id="t",
        user_ctx=UserCtx(
            tenant_id="t1", user_id="u1", roles=["a"], data_scope={}, permissions=["*"]
        ),
    )
    session.messages.append(Message(role=Role.user, content=[TextBlock("产出报告")]))
    _ = [e async for e in orch.advance(session)]

    fails = [v for v in session.verdicts if not v["ok"]]
    assert len(fails) == 3  # 1 次 + 2 次重试 = 3 次校验,均失败(≤2 次回流重试)
    assert session.replan_count == 1
