"""e2e 集:jsonl 剧本 → MockProvider(路由)+ stub 注册表 → 编排器,核对终态/事件。

覆盖跨能力诊断、计划确认、失败重排(replan)、预算耗尽部分结论等编排路径。
剧本仅描述"模型会怎么走 + 期望终态性质",不含任何业务标准答案(§10 反模式)。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from contracts import ToolSpec, UserCtx
from contracts.models import ErrorCode, SideEffect
from llm import Message, MockProvider, Role, ScriptedTurn, TextBlock, ToolUseBlock
from orchestrator import (
    AnswerDeltaEvent,
    AskUserEvent,
    Budget,
    ConfirmRequestEvent,
    DoneEvent,
    Orchestrator,
    OrchestratorEvent,
    PlanEvent,
    Session,
    ToolContext,
    ToolOutcome,
    ToolRegistry,
    ToolResultSummaryEvent,
)

from ..framework import Case, CaseResult, SetResult, cases_path, load_jsonl, run_cases

_FINAL_MARK = "请综合各步骤产物作答"
_REPLAN_MARK = "请用 update_plan"
_CRITIQUE_MARK = "校验未通过"
_STEP_MARK = "执行步骤 "

_EVENT_TYPES: dict[str, type[OrchestratorEvent]] = {
    "AnswerDeltaEvent": AnswerDeltaEvent,
    "AskUserEvent": AskUserEvent,
    "ConfirmRequestEvent": ConfirmRequestEvent,
    "DoneEvent": DoneEvent,
    "PlanEvent": PlanEvent,
    "ToolResultSummaryEvent": ToolResultSummaryEvent,
}


def _uc() -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=["*"]
    )


def _last_user_text(messages: Sequence[Message]) -> str:
    for msg in reversed(list(messages)):
        if msg.role == Role.user:
            for block in msg.content:
                if isinstance(block, TextBlock):
                    return block.text
    return ""


def _plan_call(plan_input: dict[str, Any]) -> ToolUseBlock:
    return ToolUseBlock(id="plan", name="update_plan", input=plan_input)


def _mk_call(spec: dict[str, Any]) -> ToolUseBlock:
    return ToolUseBlock(
        id=str(spec.get("id", "c")), name=str(spec["name"]), input=dict(spec.get("input", {}))
    )


def _stub_spec(name: str, scope: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"e2e stub:{name}",
        input_schema={"type": "object", "additionalProperties": True},
        output_schema={"type": "object"},
        permission_scope=scope,
        side_effects=SideEffect.read,
        confirmation_required=False,
        timeout_ms=10000,
        errors=[ErrorCode.VALIDATION_FAILED],
    )


def _stub_registry() -> ToolRegistry:
    registry = ToolRegistry()

    async def ok(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        return ToolOutcome(summary="(stub) 完成 3 行", raw={"rows": 3})

    registry.register(_stub_spec("query_finance_data", "data.read.query"), ok)
    registry.register(_stub_spec("search_knowledge", "rag.read.search"), ok)
    return registry


def _make_router(d: dict[str, Any]) -> Callable[[Sequence[Message]], ScriptedTurn]:
    plans: list[dict[str, Any]] = d.get("plans", [])
    step_results: dict[str, dict[str, Any]] = d.get("step_results", {})
    final_text = str(d.get("final_text", "(完成)"))
    answer_text = str(d.get("answer_text", "(完成)"))
    plan_tools: list[dict[str, Any]] = d.get("plan_tools", [])
    state: dict[str, Any] = {"plan_i": 0, "tool_emitted": False}

    def router(messages: Sequence[Message]) -> ScriptedTurn:
        last = _last_user_text(messages)
        if _FINAL_MARK in last:
            return ScriptedTurn(text=final_text, stop_reason="end_turn")
        if _CRITIQUE_MARK in last:  # 失败步重试:沿用不存在的工具 → 继续失败
            return ScriptedTurn(
                tool_calls=[ToolUseBlock(id="retry", name="missing_probe", input={})],
                stop_reason="tool_use",
            )
        for sid, spec in step_results.items():
            if f"{_STEP_MARK}{sid}" in last:
                if spec.get("fail"):
                    return ScriptedTurn(
                        tool_calls=[ToolUseBlock(id=f"{sid}f", name="missing_probe", input={})],
                        stop_reason="tool_use",
                    )
                return ScriptedTurn(text=str(spec.get("text", sid)), stop_reason="end_turn")
        if _REPLAN_MARK in last and plans:
            i = min(state["plan_i"], len(plans) - 1)
            state["plan_i"] = i + 1
            return ScriptedTurn(tool_calls=[_plan_call(plans[i])], stop_reason="tool_use")
        if plan_tools and not state["tool_emitted"]:
            state["tool_emitted"] = True
            return ScriptedTurn(
                tool_calls=[_mk_call(t) for t in plan_tools], stop_reason="tool_use"
            )
        if plans and state["plan_i"] == 0:  # planning 首轮
            state["plan_i"] = 1
            return ScriptedTurn(tool_calls=[_plan_call(plans[0])], stop_reason="tool_use")
        return ScriptedTurn(text=answer_text, stop_reason="end_turn")

    return router


def _check(case: Case, events: list[OrchestratorEvent], session: Session) -> CaseResult:
    exp = case.data["expect"]
    names = [type(e).__name__ for e in events]
    problems: list[str] = []
    for required in exp.get("events_include", []):
        if required not in names:
            problems.append(f"缺事件 {required}")
    if "stop_reason" in exp:
        dones = [e for e in events if isinstance(e, DoneEvent)]
        got = dones[-1].stop_reason if dones else None
        if got != exp["stop_reason"]:
            problems.append(f"stop_reason={got} 期望 {exp['stop_reason']}")
    if "min_plan_events" in exp:
        n = sum(1 for e in events if isinstance(e, PlanEvent))
        if n < int(exp["min_plan_events"]):
            problems.append(f"PlanEvent={n} < {exp['min_plan_events']}")
    if "plan_steps" in exp:
        plan_evs = [e for e in events if isinstance(e, PlanEvent)]
        n = len(plan_evs[-1].steps) if plan_evs else 0
        if n != int(exp["plan_steps"]):
            problems.append(f"末计划步数={n} 期望 {exp['plan_steps']}")
    if exp.get("paused") and session.pending is None:
        problems.append("期望暂停但未暂停")
    return CaseResult(case.id, not problems, "; ".join(problems))


async def _score(case: Case) -> CaseResult:
    d = case.data
    provider = MockProvider(router=_make_router(d))
    budget = Budget(**d["budget"]) if "budget" in d else Budget()
    orch = Orchestrator(provider=provider, registry=_stub_registry(), budget=budget)
    session = Session(session_id="e2e", trace_id=f"e2e-{case.id}", user_ctx=_uc())
    orch.seed_user_message(session, str(d.get("user_message", "请处理")))

    events = [e async for e in orch.advance(session)]
    resume = d.get("resume")
    if resume is not None and session.pending is not None:
        kwargs: dict[str, Any] = {}
        if "confirm" in resume:
            kwargs["confirmation"] = {"confirmed": bool(resume["confirm"])}
        if "answers" in resume:
            kwargs["answers"] = dict(resume["answers"])
        events += [e async for e in orch.resume(session, **kwargs)]
    return _check(case, events, session)


async def run(threshold: float) -> SetResult:
    cases = load_jsonl(cases_path("e2e"))
    return await run_cases("e2e", cases, _score, threshold)
