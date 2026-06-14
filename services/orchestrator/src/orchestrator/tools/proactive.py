"""主动性助手域工具 handler(§5.5;红线 4:确认/订阅制 + 全量审计,不触达业务数据)。

schedule_task:首次创建经 confirm_request 确认(复用 stage-8 工具确认机制);list/cancel 仅本人;
notify:白名单模板 + 频控;escalate_to_human:工单 + 上下文移交(按接收方脱敏)。全部 structlog 审计。
"""

from __future__ import annotations

import contextlib
from typing import Any

import structlog

from scheduler_svc import (
    EscalationService,
    NotifyService,
    ScheduleAccessError,
    ScheduleNotFoundError,
    Scheduler,
)
from scheduler_svc.notify import (
    ChannelNotConfiguredError,
    RateLimitedError,
    TemplateNotFoundError,
)

from ..registry import ResumeHandler, ToolConfirmation, ToolHandler, ToolOutcome
from ..tool_context import ToolContext

_log = structlog.get_logger("orchestrator.tools.proactive")


def make_schedule_task_handler(scheduler: Scheduler) -> tuple[ToolHandler, ResumeHandler]:
    async def schedule_task(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        cron = str(args.get("cron", ""))
        action = str(args.get("action", ""))
        budget = args.get("budget") or {}
        task = scheduler.create(
            ctx.user_ctx,
            cron=cron,
            action=action,
            max_runs=budget.get("max_runs"),
            max_cost=budget.get("max_cost"),
        )
        _log.info(
            "schedule_create_pending",
            schedule_id=task.schedule_id,
            tenant_id=ctx.user_ctx.tenant_id,
            user_id=ctx.user_ctx.user_id,
            trace_id=ctx.trace_id,
        )
        return ToolOutcome(
            summary=f"待确认定时订阅(cron={cron}):{action}",
            raw={"schedule_id": task.schedule_id},
            confirmation=ToolConfirmation(
                token=task.schedule_id, prompt=f"确认创建定时订阅?cron={cron},动作:{action}"
            ),
        )

    async def resume(token: str, confirmed: bool, ctx: ToolContext) -> ToolOutcome:
        if not confirmed:
            with contextlib.suppress(ScheduleNotFoundError, ScheduleAccessError):
                scheduler.cancel(token, ctx.user_ctx)
            return ToolOutcome(summary="已放弃创建定时订阅", raw={"schedule_id": token})
        try:
            task = scheduler.confirm(token, ctx.user_ctx)
        except ScheduleNotFoundError:
            return ToolOutcome(summary="订阅不存在", is_error=True)
        except ScheduleAccessError:
            return ToolOutcome(summary="无权确认该订阅", is_error=True)
        _log.info(
            "schedule_activated",
            schedule_id=token,
            tenant_id=ctx.user_ctx.tenant_id,
            user_id=ctx.user_ctx.user_id,
            trace_id=ctx.trace_id,
        )
        return ToolOutcome(summary=f"定时订阅已生效:{task.cron}", raw={"schedule_id": token})

    return schedule_task, resume


def make_list_schedules_handler(scheduler: Scheduler) -> ToolHandler:
    async def list_schedules(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        views = scheduler.list_schedules(
            ctx.user_ctx, active_only=bool(args.get("active_only", False))
        )
        return ToolOutcome(
            summary=f"{len(views)} 个定时订阅", raw={"schedules": [v.model_dump() for v in views]}
        )

    return list_schedules


def make_cancel_schedule_handler(scheduler: Scheduler) -> ToolHandler:
    async def cancel_schedule(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        schedule_id = str(args.get("schedule_id", ""))
        try:
            cancelled = scheduler.cancel(schedule_id, ctx.user_ctx)
        except ScheduleNotFoundError:
            return ToolOutcome(summary="订阅不存在", is_error=True)
        except ScheduleAccessError:
            return ToolOutcome(summary="无权取消该订阅", is_error=True)
        _log.info(
            "schedule_cancelled",
            schedule_id=schedule_id,
            tenant_id=ctx.user_ctx.tenant_id,
            user_id=ctx.user_ctx.user_id,
            trace_id=ctx.trace_id,
        )
        return ToolOutcome(summary="已退订", raw={"cancelled": cancelled})

    return cancel_schedule


def make_notify_handler(notify_service: NotifyService) -> ToolHandler:
    async def notify(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        template_id = str(args.get("template_id", ""))
        channel = str(args.get("channel", "inapp"))
        try:
            delivered = notify_service.send(
                ctx.user_ctx,
                template_id=template_id,
                channel=channel,
                params=dict(args.get("params") or {}),
            )
        except TemplateNotFoundError:
            return ToolOutcome(summary="模板不在白名单", is_error=True)
        except RateLimitedError:
            return ToolOutcome(summary="发送过于频繁,请稍后再试", is_error=True)
        except ChannelNotConfiguredError:
            return ToolOutcome(summary="通知通道未配置", is_error=True)
        _log.info(
            "notify",
            template_id=template_id,
            channel=channel,
            tenant_id=ctx.user_ctx.tenant_id,
            user_id=ctx.user_ctx.user_id,
            trace_id=ctx.trace_id,
        )
        return ToolOutcome(summary="已发送通知", raw={"delivered": delivered})

    return notify


def make_escalate_handler(escalation_service: EscalationService) -> ToolHandler:
    async def escalate_to_human(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        ticket = escalation_service.escalate(
            ctx.user_ctx,
            summary=str(args.get("summary", "")),
            context_refs=[str(r) for r in (args.get("context_refs") or [])],
            priority=str(args.get("priority") or "normal"),
        )
        _log.info(
            "escalate",
            ticket_id=ticket.ticket_id,
            priority=ticket.priority,
            tenant_id=ctx.user_ctx.tenant_id,
            user_id=ctx.user_ctx.user_id,
            trace_id=ctx.trace_id,
        )
        return ToolOutcome(
            summary=f"已转人工,工单 {ticket.ticket_id}", raw={"ticket_id": ticket.ticket_id}
        )

    return escalate_to_human
