"""主动性工具:schedule_task 确认流、notify 频控、escalate;助手域写均产生审计事件(红线 4)。"""

from __future__ import annotations

from pathlib import Path

from structlog.testing import capture_logs

from contracts import UserCtx
from llm import Message, MockProvider, Role, ScriptedTurn, TextBlock, ToolUseBlock
from orchestrator import (
    ConfirmRequestEvent,
    Orchestrator,
    Session,
    ToolContext,
    ToolRegistry,
    ToolResultSummaryEvent,
)
from orchestrator.tools import (
    make_cancel_schedule_handler,
    make_escalate_handler,
    make_notify_handler,
    make_schedule_task_handler,
)
from orchestrator.workspace import Workspace
from scheduler_svc import (
    ConsoleChannel,
    EscalationService,
    FileTicketGateway,
    NotifyService,
    RateLimiter,
    Scheduler,
    SqliteScheduleStore,
    TemplateStore,
)

_TEMPLATES = Path(__file__).parents[3] / "assets" / "notify-templates"


def _uc() -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=["*"]
    )


def _ctx() -> ToolContext:
    return ToolContext(user_ctx=_uc(), workspace=Workspace(), trace_id="t-proactive")


def _notify_params() -> dict[str, str]:
    return {"report_name": "月报", "period": "2026-05"}


async def test_schedule_task_confirm_flow_and_audit() -> None:
    scheduler = Scheduler(store=SqliteScheduleStore())
    registry = ToolRegistry()
    handler, resume = make_schedule_task_handler(scheduler)
    registry.register_from_contracts({"schedule_task": handler}, resumes={"schedule_task": resume})
    provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[
                    ToolUseBlock(
                        id="s1", name="schedule_task", input={"cron": "@daily", "action": "发日报"}
                    )
                ],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text="订阅已创建", stop_reason="end_turn"),
        ]
    )
    orch = Orchestrator(provider=provider, registry=registry)
    session = Session(session_id="s", trace_id="t", user_ctx=_uc())
    session.messages.append(Message(role=Role.user, content=[TextBlock("订阅日报")]))

    with capture_logs() as logs:
        seg1 = [e async for e in orch.advance(session)]
        assert any(isinstance(e, ConfirmRequestEvent) for e in seg1)  # 首次创建必须确认
        seg2 = [e async for e in orch.resume(session, confirmation={"confirmed": True})]

    summaries = [e.summary for e in seg2 if isinstance(e, ToolResultSummaryEvent)]
    assert any("生效" in s for s in summaries)
    views = scheduler.list_schedules(_uc())
    assert len(views) == 1 and views[0].active is True
    events = [entry.get("event") for entry in logs]
    assert "schedule_create_pending" in events and "schedule_activated" in events  # 审计


async def test_notify_handler_rate_limit_and_audit() -> None:
    service = NotifyService(
        channel=ConsoleChannel(),
        templates=TemplateStore(_TEMPLATES),
        rate_limiter=RateLimiter(per_hour=1),
    )
    handler = make_notify_handler(service)
    with capture_logs() as logs:
        first = await handler(
            {"template_id": "report-ready", "channel": "inapp", "params": _notify_params()}, _ctx()
        )
        second = await handler(
            {"template_id": "report-ready", "channel": "inapp", "params": _notify_params()}, _ctx()
        )
    assert first.raw["delivered"] is True
    assert second.is_error  # 频控触发
    assert any(entry.get("event") == "notify" for entry in logs)  # 审计


async def test_escalate_handler_writes_ticket_and_audit(tmp_path: Path) -> None:
    service = EscalationService(gateway=FileTicketGateway(tmp_path))
    handler = make_escalate_handler(service)
    with capture_logs() as logs:
        out = await handler({"summary": "客户投诉,联系 13800138000", "priority": "high"}, _ctx())
    assert out.raw["ticket_id"]
    assert any(entry.get("event") == "escalate" for entry in logs)  # 审计
    assert list(tmp_path.glob("*.json"))  # 工单落盘


async def test_cancel_schedule_handler_and_audit() -> None:
    scheduler = Scheduler(store=SqliteScheduleStore())
    task = scheduler.create(_uc(), cron="@daily", action="x")
    scheduler.confirm(task.schedule_id, _uc(), now=0.0)
    handler = make_cancel_schedule_handler(scheduler)
    with capture_logs() as logs:
        out = await handler({"schedule_id": task.schedule_id}, _ctx())
    assert out.raw["cancelled"] is True
    assert any(entry.get("event") == "schedule_cancelled" for entry in logs)
