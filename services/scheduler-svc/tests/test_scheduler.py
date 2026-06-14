"""定时调度:确认激活、origin=scheduled 触发、预算/连续失败停用、list/cancel 归属。"""

from __future__ import annotations

import pytest

from contracts import UserCtx
from scheduler_svc import (
    ScheduleAccessError,
    ScheduledTask,
    Scheduler,
    SqliteScheduleStore,
    SubmitResult,
)


def _uc(tenant: str = "t1", user: str = "u1") -> UserCtx:
    return UserCtx(
        tenant_id=tenant, user_id=user, roles=["analyst"], data_scope={}, permissions=["*"]
    )


class _FakeSubmitter:
    def __init__(self, result: SubmitResult | None = None) -> None:
        self.result = result or SubmitResult(ok=True)
        self.calls: list[tuple[str, str]] = []

    def submit(self, task: ScheduledTask, *, origin: str) -> SubmitResult:
        self.calls.append((task.schedule_id, origin))
        return self.result


def _scheduler(submitter: _FakeSubmitter | None = None, *, max_failures: int = 3) -> Scheduler:
    return Scheduler(store=SqliteScheduleStore(), submitter=submitter, max_failures=max_failures)


def _active(sched: Scheduler, uc: UserCtx, schedule_id: str) -> bool:
    return next(v.active for v in sched.list_schedules(uc) if v.schedule_id == schedule_id)


def test_create_then_confirm_activates() -> None:
    sched = _scheduler()
    uc = _uc()
    task = sched.create(uc, cron="*/5 * * * *", action="发月报")
    assert not task.active and not task.confirmed  # 首次创建未激活,待确认
    confirmed = sched.confirm(task.schedule_id, uc, now=0.0)
    assert confirmed.active and confirmed.confirmed


def test_tick_submits_with_scheduled_origin() -> None:
    submitter = _FakeSubmitter()
    sched = _scheduler(submitter)
    uc = _uc()
    task = sched.create(uc, cron="*/1 * * * *", action="发月报")
    sched.confirm(task.schedule_id, uc, now=0.0)  # next_run=60
    assert sched.tick(now=100.0) == [task.schedule_id]
    assert submitter.calls == [(task.schedule_id, "scheduled")]


def test_max_runs_deactivates() -> None:
    submitter = _FakeSubmitter()
    sched = _scheduler(submitter)
    uc = _uc()
    task = sched.create(uc, cron="*/1 * * * *", action="x", max_runs=2)
    sched.confirm(task.schedule_id, uc, now=0.0)
    sched.tick(now=100.0)
    sched.tick(now=400.0)  # 第 2 次 → 达 max_runs → 停用
    assert sched.tick(now=700.0) == []  # 已停用,不再触发
    assert _active(sched, uc, task.schedule_id) is False
    assert len(submitter.calls) == 2


def test_max_cost_deactivates() -> None:
    submitter = _FakeSubmitter(SubmitResult(ok=True, cost=3.0))
    sched = _scheduler(submitter)
    uc = _uc()
    task = sched.create(uc, cron="*/1 * * * *", action="x", max_runs=100, max_cost=5.0)
    sched.confirm(task.schedule_id, uc, now=0.0)
    sched.tick(now=100.0)  # cost 3 < 5
    sched.tick(now=400.0)  # cost 6 >= 5 → 停用
    assert _active(sched, uc, task.schedule_id) is False


def test_consecutive_failures_deactivate() -> None:
    submitter = _FakeSubmitter(SubmitResult(ok=False))
    sched = _scheduler(submitter, max_failures=2)
    uc = _uc()
    task = sched.create(uc, cron="*/1 * * * *", action="x", max_runs=100)
    sched.confirm(task.schedule_id, uc, now=0.0)
    sched.tick(now=100.0)  # 失败 1
    sched.tick(now=400.0)  # 失败 2 → 停用
    assert _active(sched, uc, task.schedule_id) is False


def test_list_and_cancel_ownership() -> None:
    sched = _scheduler()
    owner = _uc("t1", "ua")
    other = _uc("t1", "ub")
    task = sched.create(owner, cron="@daily", action="x")
    sched.confirm(task.schedule_id, owner, now=0.0)
    assert len(sched.list_schedules(owner)) == 1
    assert sched.list_schedules(other) == []  # 跨用户不可见
    with pytest.raises(ScheduleAccessError):
        sched.cancel(task.schedule_id, other)  # 非本人不可取消(归属)
    assert sched.cancel(task.schedule_id, owner) is True
