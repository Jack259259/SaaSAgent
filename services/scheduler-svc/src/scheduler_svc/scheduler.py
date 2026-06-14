"""定时订阅调度(方案 §5.5)。

任务以创建者 user_ctx 身份运行;首次需 confirm 激活;每任务预算(max_runs/max_cost)+ 连续失败阈值
达限自动停用;tick 对到期任务经 TaskSubmitter 提交带 origin="scheduled" 的会话任务。
list/cancel 仅限本人任务(归属校验,红线 3/9)。**不触达业务数据写**(红线 4)。
"""

from __future__ import annotations

import time
import uuid
from typing import Protocol

from contracts import UserCtx

from .cron import next_run
from .models import ScheduledTask, ScheduleView, SubmitResult
from .store import ScheduleStore, SqliteScheduleStore

_MAX_CONSECUTIVE_FAILURES = 3


class TaskSubmitter(Protocol):
    """触发时把任务作为会话提交给编排器(origin=scheduled)。生产由网关实现。"""

    def submit(self, task: ScheduledTask, *, origin: str) -> SubmitResult: ...


class ScheduleNotFoundError(Exception): ...


class ScheduleAccessError(Exception):
    """非本人任务(归属校验失败)。"""


class Scheduler:
    def __init__(
        self,
        *,
        store: ScheduleStore | None = None,
        submitter: TaskSubmitter | None = None,
        max_failures: int = _MAX_CONSECUTIVE_FAILURES,
    ) -> None:
        self._store = store or SqliteScheduleStore()
        self._submitter = submitter
        self._max_failures = max_failures

    def create(
        self,
        user_ctx: UserCtx,
        *,
        cron: str,
        action: str,
        max_runs: int | None = None,
        max_cost: float | None = None,
    ) -> ScheduledTask:
        task = ScheduledTask(
            schedule_id=uuid.uuid4().hex,
            tenant_id=user_ctx.tenant_id,
            user_id=user_ctx.user_id,
            cron=cron,
            action=action,
        )
        if max_runs is not None:
            task.max_runs = max_runs
        if max_cost is not None:
            task.max_cost = max_cost
        self._store.add(task)  # confirmed=False, active=False:等首次确认
        return task

    def confirm(
        self, schedule_id: str, user_ctx: UserCtx, *, now: float | None = None
    ) -> ScheduledTask:
        task = self._owned(schedule_id, user_ctx)
        task.confirmed = True
        task.active = True
        task.next_run_at = next_run(task.cron, now if now is not None else time.time())
        self._store.update(task)
        return task

    def cancel(self, schedule_id: str, user_ctx: UserCtx) -> bool:
        task = self._owned(schedule_id, user_ctx)
        task.active = False
        self._store.update(task)
        return True

    def list_schedules(self, user_ctx: UserCtx, *, active_only: bool = False) -> list[ScheduleView]:
        return [
            ScheduleView(schedule_id=t.schedule_id, cron=t.cron, active=t.active)
            for t in self._store.list_by_user(user_ctx.tenant_id, user_ctx.user_id)
            if t.active or not active_only
        ]

    def tick(self, now: float | None = None) -> list[str]:
        moment = now if now is not None else time.time()
        triggered: list[str] = []
        for task in self._store.due(moment):
            if task.runs_used >= task.max_runs:  # 预算(次数)已耗尽
                task.active = False
                self._store.update(task)
                continue
            result = (
                self._submitter.submit(task, origin="scheduled")
                if self._submitter is not None
                else SubmitResult(ok=True)
            )
            task.runs_used += 1
            task.cost_used += result.cost
            task.consecutive_failures = 0 if result.ok else task.consecutive_failures + 1
            if (
                task.runs_used >= task.max_runs
                or task.cost_used >= task.max_cost
                or task.consecutive_failures >= self._max_failures
            ):
                task.active = False  # 预算耗尽 / 连续失败 → 自动停用
            else:
                task.next_run_at = next_run(task.cron, moment)
            self._store.update(task)
            triggered.append(task.schedule_id)
        return triggered

    def _owned(self, schedule_id: str, user_ctx: UserCtx) -> ScheduledTask:
        task = self._store.get(schedule_id)
        if task is None:
            raise ScheduleNotFoundError(schedule_id)
        if task.tenant_id != user_ctx.tenant_id or task.user_id != user_ctx.user_id:
            raise ScheduleAccessError(schedule_id)  # 归属(红线 3/9)
        return task
