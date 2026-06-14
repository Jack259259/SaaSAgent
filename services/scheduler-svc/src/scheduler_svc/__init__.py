"""scheduler-svc:定时订阅 + 模板化通知 + 转人工(助手域副作用,方案 §5.5)。

对外能力经 schedule_task / list_schedules / cancel_schedule / notify / escalate_to_human 契约。
全部确认或订阅制 + 全量审计,不触达业务数据写路径(红线 4)。
"""

from __future__ import annotations

from .escalation import EscalationService, FileTicketGateway, TicketGateway
from .models import ScheduledTask, ScheduleView, SubmitResult, Ticket
from .notify import (
    ChannelNotConfiguredError,
    ConsoleChannel,
    NotifyChannel,
    NotifyService,
    RateLimitedError,
    RateLimiter,
    TemplateNotFoundError,
    TemplateStore,
    WebhookChannel,
)
from .scheduler import (
    ScheduleAccessError,
    ScheduleNotFoundError,
    Scheduler,
    TaskSubmitter,
)
from .store import ScheduleStore, SqliteScheduleStore

__version__ = "0.1.0"

__all__ = [
    "ChannelNotConfiguredError",
    "ConsoleChannel",
    "EscalationService",
    "FileTicketGateway",
    "NotifyChannel",
    "NotifyService",
    "RateLimitedError",
    "RateLimiter",
    "ScheduleAccessError",
    "ScheduleNotFoundError",
    "ScheduleStore",
    "ScheduleView",
    "ScheduledTask",
    "Scheduler",
    "SqliteScheduleStore",
    "SubmitResult",
    "TaskSubmitter",
    "TemplateNotFoundError",
    "TemplateStore",
    "Ticket",
    "TicketGateway",
    "WebhookChannel",
    "__version__",
]
