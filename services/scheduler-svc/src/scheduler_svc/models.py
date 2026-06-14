"""scheduler-svc 模型(方案 §5.5,助手域副作用)。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_FORBID = ConfigDict(extra="forbid")

_DEFAULT_MAX_RUNS = 30
_DEFAULT_MAX_COST = 10.0


class ScheduledTask(BaseModel):
    """定时订阅任务(以创建者身份运行;每任务预算 + 连续失败停用)。"""

    model_config = _FORBID

    schedule_id: str
    tenant_id: str
    user_id: str
    cron: str
    action: str
    max_runs: int = _DEFAULT_MAX_RUNS
    max_cost: float = _DEFAULT_MAX_COST
    runs_used: int = 0
    cost_used: float = 0.0
    consecutive_failures: int = 0
    confirmed: bool = False
    active: bool = False
    next_run_at: float = 0.0  # epoch seconds


class SubmitResult(BaseModel):
    """TaskSubmitter 触发后的结果(回灌预算 / 失败计数)。"""

    model_config = _FORBID

    ok: bool
    cost: float = 0.0


class ScheduleView(BaseModel):
    model_config = _FORBID

    schedule_id: str
    cron: str
    active: bool


class Ticket(BaseModel):
    model_config = _FORBID

    ticket_id: str
    tenant_id: str
    user_id: str
    summary: str
    context_refs: list[str] = Field(default_factory=list)
    priority: str = "normal"
    created_at: str = ""
