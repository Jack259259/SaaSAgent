"""自研薄编排循环:ReAct 地板 + Plan&Execute 外层 + 行内反思(方案 §4)。

阶段 3:在 ReAct 之上叠加 Plan&Execute——模型经 update_plan 显式建/改计划,编排器驱动执行
(按 depends_on 拓扑分波并行、写步骤确认暂停、步骤产物入工作区、每步行内反思校验、失败 replan)。
跨请求暂停/恢复经 Session + advance/resume 实现。简单任务仍走 ReAct 直接作答。

注:Plan&Execute 引擎方法与 ReAct 共享 Session/工作区/校验器/审计,故同置于本文件
(对应计划中的 plan_execute.py 职责),避免紧耦合方法跨模块的循环依赖。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from contracts import UserCtx
from contracts.loader import load_toolspecs
from contracts.models import (
    AuditWho,
    CapabilityHint,
    ErrorCode,
    Plan,
    ResultStatus,
    Step,
    StepStatus,
)
from llm import (
    LlmResponse,
    Message,
    Provider,
    Role,
    StreamDone,
    TextBlock,
    TextDelta,
    ToolDef,
    ToolResultBlock,
    ToolUseBlock,
    assistant_message,
    tool_results_message,
)

from .audit import digest_args, emit_audit, who_from_user_ctx
from .compaction import Compactor, TruncationCompactor
from .events import (
    AnswerDeltaEvent,
    AskUserEvent,
    ConfirmRequestEvent,
    DoneEvent,
    OrchestratorEvent,
    PlanEvent,
    StepEvent,
    ToolCallEvent,
    ToolResultSummaryEvent,
)
from .permissions import NoPermissionError
from .reflection import VerifierRegistry
from .registry import ToolOutcome, ToolRegistry
from .session import Pending, Session
from .system_prompt import build_system_prompt
from .tool_context import ToolContext

_ANSWER_CHUNK = 64
_NOTE_MAX = 200
_MAX_STEP_RETRIES = 2  # 行内反思失败回流重试上限(§4.1)
_MAX_REPLANS = 2
_INTERCEPTED = ("update_plan", "ask_user")
_CAP_VALUES = {c.value for c in CapabilityHint}


@dataclass
class Budget:
    max_steps: int = 8
    max_cost: float = 5.0
    max_tokens: int | None = None  # None=不限;子 Agent 用它做独立 token 预算(§5.1)


def _chunks(text: str, n: int) -> Iterator[str]:
    for i in range(0, len(text), n):
        yield text[i : i + n]


def _build_plan(args: dict[str, Any], prev: Plan | None) -> Plan:
    steps: list[Step] = []
    for i, raw in enumerate(args.get("steps", [])):
        cap = raw.get("capability_hint")
        steps.append(
            Step(
                id=str(raw.get("id") or f"s{i}"),
                goal=str(raw.get("goal", "")),
                status=StepStatus.pending,
                capability_hint=CapabilityHint(cap) if cap in _CAP_VALUES else None,
                depends_on=[str(d) for d in raw.get("depends_on", [])],
                needs_confirmation=bool(raw.get("needs_confirmation", False)),
            )
        )
    version = (prev.version + 1) if prev is not None else 0
    return Plan(version=version, steps=steps)


def _step_dict(step: Step) -> dict[str, Any]:
    return {
        "id": step.id,
        "goal": step.goal,
        "capability_hint": step.capability_hint.value if step.capability_hint else None,
        "depends_on": list(step.depends_on),
        "status": step.status.value,
        "needs_confirmation": step.needs_confirmation,
    }


class Orchestrator:
    def __init__(
        self,
        *,
        provider: Provider,
        registry: ToolRegistry,
        verifiers: VerifierRegistry | None = None,
        compactor: Compactor | None = None,
        budget: Budget | None = None,
        no_progress_limit: int = 2,
        system_prompt: Callable[[], str] | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._verifiers = verifiers or VerifierRegistry()
        self._compactor = compactor or TruncationCompactor()
        self._budget = budget or Budget()
        self._no_progress_limit = no_progress_limit
        # 可注入系统提示(子 Agent 用 §5.1 专属协议提示);默认仍是主 Agent 提示。
        self._system_prompt = system_prompt
        # update_plan / ask_user 由循环拦截,但仍需把其 ToolDef 暴露给 LLM 以便其调用。
        by_name = {ls.spec.name: ls.spec for ls in load_toolspecs()}
        self._intercept_defs = [
            ToolDef(
                name=n, description=by_name[n].description, input_schema=by_name[n].input_schema
            )
            for n in _INTERCEPTED
            if n in by_name
        ]

    # ---- 公开入口 --------------------------------------------------------- #
    async def run(
        self,
        *,
        user_ctx: UserCtx,
        user_message: str,
        trace_id: str,
        page_context: dict[str, Any] | None = None,
    ) -> AsyncIterator[OrchestratorEvent]:
        """便捷入口(临时会话,不入存储):简单任务一趟跑完;若遇暂停则停在暂停点。"""
        session = Session(
            session_id="ephemeral", trace_id=trace_id, user_ctx=user_ctx, page_context=page_context
        )
        session.messages.append(Message(role=Role.user, content=[TextBlock(user_message)]))
        async for event in self.advance(session):
            yield event

    def seed_user_message(self, session: Session, user_message: str) -> None:
        session.messages.append(Message(role=Role.user, content=[TextBlock(user_message)]))

    async def advance(self, session: Session) -> AsyncIterator[OrchestratorEvent]:
        """驱动会话直到下一个暂停点(设置 session.pending)或完成(phase=done)。"""
        while session.phase != "done" and session.pending is None:
            phase = session.phase
            if phase == "planning":
                async for event in self._plan_phase(session):
                    yield event
            elif phase == "executing":
                async for event in self._exec_phase(session):
                    yield event
            elif phase == "finalizing":
                async for event in self._final_phase(session):
                    yield event
            else:
                break
            if session.phase == phase and session.pending is None:
                break  # 防御:阶段未推进也未暂停,避免空转

    async def resume(
        self,
        session: Session,
        *,
        confirmation: dict[str, Any] | None = None,
        answers: dict[str, Any] | None = None,
    ) -> AsyncIterator[OrchestratorEvent]:
        """收到 /chat/confirm 回执后恢复执行。"""
        pending = session.pending
        if pending is not None and pending.kind == "confirm":
            confirmed = bool(confirmation and confirmation.get("confirmed"))
            if confirmed and pending.step_id is not None:
                session.confirmed_step_ids.add(pending.step_id)
            elif pending.step_id is not None and session.plan is not None:
                for step in session.plan.steps:
                    if step.id == pending.step_id:
                        step.status = StepStatus.skipped
        elif pending is not None and pending.kind == "ask_user":
            content = json.dumps(answers or {}, ensure_ascii=False)
            session.messages.append(
                tool_results_message([ToolResultBlock(pending.tool_use_id or "ask_user", content)])
            )
        elif pending is not None and pending.kind == "tool_confirm":
            confirmed = bool(confirmation and confirmation.get("confirmed"))
            outcome = await self._registry.resume_tool(
                pending.tool_name or "",
                pending.confirm_token or "",
                confirmed,
                self._tool_context(session),
            )
            ref = session.workspace.put(
                key=pending.tool_name or "tool",
                type="tool_result",
                summary=outcome.summary,
                raw=outcome.raw,
            )
            yield ToolResultSummaryEvent(
                id=pending.confirm_token or "",
                tool=pending.tool_name or "",
                summary=outcome.summary,
                workspace_ref=ref,
            )
            # 续行结果作为数据消息回灌(原 tool_use 已应答 paused 结果)。
            session.messages.append(
                Message(role=Role.user, content=[TextBlock(f"[SOP 续行结果] {outcome.summary}")])
            )
        session.pending = None
        async for event in self.advance(session):
            yield event

    # ---- 规划阶段(ReAct + 触发 Plan&Execute / ask_user)------------------ #
    async def _plan_phase(self, session: Session) -> AsyncIterator[OrchestratorEvent]:
        who = who_from_user_ctx(session.user_ctx)
        ctx = self._tool_context(session)
        no_progress = 0
        while True:
            if self._budget_exhausted(session):
                yield AnswerDeltaEvent("(已达预算上限,返回阶段性结论;未尽事项可继续追问。)")
                yield DoneEvent(stop_reason="budget_exhausted", used_steps=session.used_steps)
                session.phase = "done"
                return

            response = await self._run_turn(session.messages)
            session.used_cost += response.usage.cost_usd
            session.used_tokens += response.usage.input_tokens + response.usage.output_tokens

            ask_call = self._find_call(response, "ask_user")
            plan_call = self._find_call(response, "update_plan")

            if ask_call is not None:
                session.messages.append(assistant_message(response))
                questions = self._questions(ask_call)
                session.pending = Pending(
                    kind="ask_user", tool_use_id=ask_call.id, questions=questions
                )
                yield AskUserEvent(id=ask_call.id, questions=questions)
                return

            if plan_call is not None:
                plan = _build_plan(plan_call.input, prev=session.plan)
                session.plan = plan
                session.mode = "plan_execute"
                session.messages.append(assistant_message(response))
                session.messages.append(
                    tool_results_message(
                        [
                            ToolResultBlock(
                                plan_call.id, f"计划 v{plan.version} 已接受,共 {len(plan.steps)} 步"
                            )
                        ]
                    )
                )
                yield PlanEvent(version=plan.version, steps=[_step_dict(s) for s in plan.steps])
                session.phase = "executing"
                return

            if response.tool_calls:
                made_progress = False
                yield StepEvent(index=session.used_steps, note=self._note(response))
                for call in response.tool_calls:
                    yield ToolCallEvent(id=call.id, tool=call.name, arguments=call.input)
                outcomes: list[ToolOutcome] = await asyncio.gather(
                    *[
                        self._exec_tool(call, ctx, who, session.trace_id)
                        for call in response.tool_calls
                    ]
                )
                result_blocks: list[ToolResultBlock] = []
                for call, outcome in zip(response.tool_calls, outcomes, strict=True):
                    ref = session.workspace.put(
                        key=call.name, type="tool_result", summary=outcome.summary, raw=outcome.raw
                    )
                    yield ToolResultSummaryEvent(
                        id=call.id, tool=call.name, summary=outcome.summary, workspace_ref=ref
                    )
                    result_blocks.append(
                        ToolResultBlock(call.id, outcome.summary, is_error=outcome.is_error)
                    )
                    made_progress = made_progress or (
                        not outcome.is_error and bool(outcome.summary.strip())
                    )
                session.messages.append(assistant_message(response))
                session.messages.append(tool_results_message(result_blocks))
                session.messages = self._compactor.compact(session.messages)
                session.used_steps += 1
                for call, outcome in zip(response.tool_calls, outcomes, strict=True):
                    conf = outcome.confirmation
                    if conf is None:
                        continue
                    # 红线 4:工具中途请求确认 → 暂停发 confirm_request,等回执续行。
                    session.pending = Pending(
                        kind="tool_confirm",
                        tool_use_id=call.id,
                        tool_name=call.name,
                        confirm_token=conf.token,
                    )
                    yield ConfirmRequestEvent(
                        id=conf.token, prompt=conf.prompt, options=["confirm", "cancel"]
                    )
                    return
                no_progress = 0 if made_progress else no_progress + 1
                if no_progress >= self._no_progress_limit:
                    yield AnswerDeltaEvent("(连续多步无新信息,停止以防打转。)")
                    yield DoneEvent(stop_reason="no_progress", used_steps=session.used_steps)
                    session.phase = "done"
                    return
                continue

            # 无工具调用 → 直接作答(简单任务)
            for chunk in _chunks(response.text or "(无内容)", _ANSWER_CHUNK):
                yield AnswerDeltaEvent(chunk)
            yield DoneEvent(stop_reason="end_turn", used_steps=session.used_steps)
            session.phase = "done"
            return

    # ---- 执行阶段(拓扑分波 + 确认闸门 + 并行 + replan)------------------- #
    async def _exec_phase(self, session: Session) -> AsyncIterator[OrchestratorEvent]:
        plan = session.plan
        if plan is None:
            session.phase = "finalizing"
            return
        while True:
            pending_steps = [
                s
                for s in plan.steps
                if s.id not in session.done_step_ids
                and s.status not in (StepStatus.failed, StepStatus.skipped)
            ]
            if not pending_steps:
                break
            ready = [s for s in pending_steps if set(s.depends_on) <= session.done_step_ids]
            if not ready:
                break  # 依赖不可满足(失败依赖 / 环)→ 转收尾出部分结论

            gate = next(
                (
                    s
                    for s in ready
                    if s.needs_confirmation and s.id not in session.confirmed_step_ids
                ),
                None,
            )
            if gate is not None:
                # 红线 4:写步骤须用户确认后才进入执行(orchestrator 侧闸门)。
                session.pending = Pending(kind="confirm", step_id=gate.id)
                yield ConfirmRequestEvent(
                    id=gate.id,
                    prompt=f"步骤『{gate.goal}』包含写操作,请确认是否执行",
                    options=["confirm", "cancel"],
                )
                return

            results = await asyncio.gather(*[self._execute_step(session, s) for s in ready])
            for step, (events, status) in sorted(
                zip(ready, results, strict=True), key=lambda pair: pair[0].id
            ):
                for event in events:
                    yield event
                step.status = status
                if status == StepStatus.done:
                    session.done_step_ids.add(step.id)
            session.used_steps += len(ready)

            failed = [s for s in ready if s.status == StepStatus.failed]
            if failed:
                if session.replan_count >= _MAX_REPLANS:
                    break
                session.replan_count += 1
                async for event in self._replan(session, failed):
                    yield event
                if session.pending is not None:
                    return
                plan = session.plan if session.plan is not None else plan
        session.phase = "finalizing"

    async def _execute_step(
        self, session: Session, step: Step
    ) -> tuple[list[OrchestratorEvent], StepStatus]:
        """单步执行(深度 1 小 ReAct + 行内反思,失败回流重试 ≤2)。不直接 yield(供并行 gather)。"""
        events: list[OrchestratorEvent] = []
        ctx = self._tool_context(session)
        who = who_from_user_ctx(session.user_ctx)
        brief = self._workspace_brief(session)
        messages = [
            *session.messages,
            Message(
                role=Role.user, content=[TextBlock(f"执行步骤 {step.id}:{step.goal}\n{brief}")]
            ),
        ]
        critique = ""
        for _attempt in range(1 + _MAX_STEP_RETRIES):
            response = await self._run_turn(messages)
            if not response.tool_calls:
                events.append(
                    StepEvent(
                        index=session.used_steps, note=(response.text or step.goal)[:_NOTE_MAX]
                    )
                )
                return events, StepStatus.done
            events.append(
                StepEvent(index=session.used_steps, note=self._note(response) or step.goal)
            )
            result_blocks: list[ToolResultBlock] = []
            step_ok = True
            for call in response.tool_calls:
                events.append(ToolCallEvent(id=call.id, tool=call.name, arguments=call.input))
                outcome = await self._exec_tool(call, ctx, who, session.trace_id)
                ref = session.workspace.put(
                    key=call.name, type="tool_result", summary=outcome.summary, raw=outcome.raw
                )
                events.append(
                    ToolResultSummaryEvent(
                        id=call.id, tool=call.name, summary=outcome.summary, workspace_ref=ref
                    )
                )
                result_blocks.append(
                    ToolResultBlock(call.id, outcome.summary, is_error=outcome.is_error)
                )
                if self._registry.has(call.name):
                    verdict = self._verifiers.verify(outcome, self._registry.spec(call.name))
                    session.verdicts.append(verdict.to_dict())
                    if not verdict.ok:
                        step_ok = False
                        critique = verdict.critique
                elif outcome.is_error:
                    step_ok = False
                    critique = outcome.summary
            if step_ok:
                return events, StepStatus.done
            messages = [
                *messages,
                assistant_message(response),
                tool_results_message(result_blocks),
                Message(
                    role=Role.user,
                    content=[TextBlock(f"上一步校验未通过:{critique}。请修正后重试。")],
                ),
            ]
        return events, StepStatus.failed

    async def _replan(
        self, session: Session, failed: list[Step]
    ) -> AsyncIterator[OrchestratorEvent]:
        detail = ", ".join(f"{s.id}({s.goal})" for s in failed)
        note = f"步骤失败:{detail}。请用 update_plan 修订计划(可局部修补或整体重排)。"
        session.messages.append(Message(role=Role.user, content=[TextBlock(note)]))
        response = await self._run_turn(session.messages)
        session.used_cost += response.usage.cost_usd
        plan_call = self._find_call(response, "update_plan")
        if plan_call is None:
            return  # 模型未重排 → 放弃,转收尾(调用方处理)
        plan = _build_plan(plan_call.input, prev=session.plan)
        for step in plan.steps:  # 局部修补:已完成步骤保留完成态
            if step.id in session.done_step_ids:
                step.status = StepStatus.done
        session.plan = plan
        session.messages.append(assistant_message(response))
        session.messages.append(
            tool_results_message([ToolResultBlock(plan_call.id, f"计划 v{plan.version} 已更新")])
        )
        yield PlanEvent(version=plan.version, steps=[_step_dict(s) for s in plan.steps])

    # ---- 收尾阶段 --------------------------------------------------------- #
    async def _final_phase(self, session: Session) -> AsyncIterator[OrchestratorEvent]:
        if self._budget_exhausted(session):
            yield AnswerDeltaEvent("(已达预算上限,返回阶段性结论。)")
            yield DoneEvent(stop_reason="budget_exhausted", used_steps=session.used_steps)
            session.phase = "done"
            return
        prompt = f"请综合各步骤产物作答。\n{self._workspace_brief(session)}"
        messages = [*session.messages, Message(role=Role.user, content=[TextBlock(prompt)])]
        response = await self._run_turn(messages)
        for chunk in _chunks(response.text or "(无结论)", _ANSWER_CHUNK):
            yield AnswerDeltaEvent(chunk)
        yield DoneEvent(stop_reason="completed", used_steps=session.used_steps)
        session.phase = "done"

    # ---- 工具与 LLM 原语 -------------------------------------------------- #
    def _tool_context(self, session: Session) -> ToolContext:
        return ToolContext(
            user_ctx=session.user_ctx,
            workspace=session.workspace,
            trace_id=session.trace_id,
            page_context=session.page_context,
        )

    def _budget_exhausted(self, session: Session) -> bool:
        return (
            session.used_steps >= self._budget.max_steps
            or session.used_cost >= self._budget.max_cost
            or (
                self._budget.max_tokens is not None
                and session.used_tokens >= self._budget.max_tokens
            )
        )

    def _workspace_brief(self, session: Session) -> str:
        briefs = session.workspace.briefs()
        return "工作区:\n" + "\n".join(briefs) if briefs else "工作区为空"

    @staticmethod
    def _note(response: LlmResponse) -> str:
        return (response.text or "").strip()[:_NOTE_MAX] or "执行工具"

    @staticmethod
    def _find_call(response: LlmResponse, name: str) -> ToolUseBlock | None:
        return next((c for c in response.tool_calls if c.name == name), None)

    @staticmethod
    def _questions(ask_call: ToolUseBlock) -> list[dict[str, Any]]:
        raw = ask_call.input.get("questions", [])
        items = [q for q in raw if isinstance(q, dict)][:3]
        return items

    async def _run_turn(self, messages: Sequence[Message]) -> LlmResponse:
        tool_defs = [*self._registry.tool_defs(), *self._intercept_defs]
        response: LlmResponse | None = None
        system = self._system_prompt() if self._system_prompt is not None else build_system_prompt()
        async for ev in self._provider.stream(system=system, messages=messages, tools=tool_defs):
            if isinstance(ev, TextDelta):
                continue
            if isinstance(ev, StreamDone):
                response = ev.response
        if response is None:
            raise RuntimeError("provider.stream 未产生 StreamDone")
        return response

    async def _exec_tool(
        self, call: ToolUseBlock, ctx: ToolContext, who: AuditWho, trace_id: str
    ) -> ToolOutcome:
        digest = digest_args(call.input)
        start = time.monotonic()
        if not self._registry.has(call.name):
            emit_audit(
                who=who,
                tool=call.name,
                args_digest=digest,
                result_status=ResultStatus.error,
                trace_id=trace_id,
                error_code=ErrorCode.NOT_FOUND,
            )
            return ToolOutcome(summary=f"工具未注册:{call.name}", is_error=True)
        try:
            outcome = await self._registry.invoke(call.name, call.input, ctx)
        except NoPermissionError:
            emit_audit(
                who=who,
                tool=call.name,
                args_digest=digest,
                result_status=ResultStatus.denied,
                trace_id=trace_id,
                error_code=ErrorCode.NO_PERMISSION,
            )
            return ToolOutcome(summary="无权限调用该工具", is_error=True)  # §6:不暴露内部细节
        except Exception:
            emit_audit(
                who=who,
                tool=call.name,
                args_digest=digest,
                result_status=ResultStatus.error,
                trace_id=trace_id,
                error_code=ErrorCode.INTERNAL_ERROR,
            )
            return ToolOutcome(summary="工具执行失败", is_error=True)
        emit_audit(
            who=who,
            tool=call.name,
            args_digest=digest,
            result_status=ResultStatus.ok,
            trace_id=trace_id,
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        return outcome
