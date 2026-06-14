"""SOP 执行器模型(方案 §5.4 / 附录 B)。

Sop:解析后的资产(extra=ignore,严格 schema 校验在 sopcheck;此处只取执行所需字段)。
RunState:可持久化运行实例(无浏览器句柄等非序列化物)。RunReport:对外运行报告。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_FORBID = ConfigDict(extra="forbid")
_IGNORE = ConfigDict(extra="ignore")


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    paused = "paused"
    succeeded = "succeeded"
    failed = "failed"


# ---- SOP 资产(解析后,执行所需子集)----------------------------------- #
class ApiCall(BaseModel):
    model_config = _IGNORE
    method: str
    path: str
    body: dict[str, Any] = Field(default_factory=dict)
    capture: dict[str, str] = Field(default_factory=dict)


class ApiBlock(BaseModel):
    model_config = _IGNORE
    calls: list[ApiCall] = Field(default_factory=list)


class UiStep(BaseModel):
    model_config = _IGNORE
    instruction: str
    action: str
    target: dict[str, str] = Field(default_factory=dict)
    value: str | None = None
    confirm: bool = False


class UiBlock(BaseModel):
    model_config = _IGNORE
    steps: list[UiStep] = Field(default_factory=list)


class Preconditions(BaseModel):
    model_config = _IGNORE
    permissions: list[str] = Field(default_factory=list)
    prerequisite_state: str | None = None
    blocking_when: str | None = None


class VerifySpec(BaseModel):
    model_config = _IGNORE
    api: dict[str, Any] = Field(default_factory=dict)  # {method, path}
    expect: dict[str, Any] = Field(default_factory=dict)


class Postconditions(BaseModel):
    model_config = _IGNORE
    human_readable: str
    verify: VerifySpec | None = None


class OnFailure(BaseModel):
    model_config = _IGNORE
    when: str
    hint: str


class InputSpec(BaseModel):
    model_config = _IGNORE
    key: str
    label: str
    type: str
    required: bool
    validation: str | None = None
    source: str | None = None


class Sop(BaseModel):
    model_config = _IGNORE
    id: str
    name: str
    description: str
    aliases: list[str] = Field(default_factory=list)
    domain: str | None = None
    side_effects: str = "read"
    requires_confirmation: bool = False
    preconditions: Preconditions = Field(default_factory=Preconditions)
    inputs: list[InputSpec] = Field(default_factory=list)
    api: ApiBlock | None = None
    ui: UiBlock | None = None
    postconditions: Postconditions
    on_failure: list[OnFailure] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


# ---- 运行态 ----------------------------------------------------------- #
class StepResult(BaseModel):
    model_config = _FORBID
    kind: str  # precondition | api | ui | postcondition | confirm
    name: str
    ok: bool
    detail: str = ""


class Confirmation(BaseModel):
    """confirm 步暂停时回传给编排器的确认请求(红线 4)。"""

    model_config = _FORBID
    run_id: str
    prompt: str
    action_preview: str


class RunState(BaseModel):
    """可持久化运行实例(RunStore 落盘;不含浏览器句柄等非序列化物)。"""

    model_config = _FORBID
    run_id: str
    sop_id: str
    status: RunStatus
    inputs: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str
    user_id: str
    captures: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False
    steps: list[StepResult] = Field(default_factory=list)
    pending_confirm: Confirmation | None = None
    failure_hint: str | None = None


class RunReport(BaseModel):
    model_config = _FORBID
    run_id: str
    sop_id: str
    status: RunStatus
    steps: list[StepResult] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)  # workspace 句柄(handler 落盘)
    failure_hint: str | None = None
    message: str = ""


class SopMatch(BaseModel):
    model_config = _FORBID
    id: str
    name: str
    score: float
