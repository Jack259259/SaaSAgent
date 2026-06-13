"""契约的 pydantic v2 运行时模型(阶段 1)。

设计约束(要求 7):**schema 文件(contracts/*.json|yaml)是唯一事实源**。
这里的模型是类型化运行时层,字段名与必填项与对应 JSON Schema 严格一致;
其一致性由 tests/test_model_schema_parity.py 守护(防漂移),由 contract-test 强制。

模型不重复表达 schema 的全部约束(如 pattern / 跨字段 if-then),那些由
validator.py 用 jsonschema 直接对着 schema 文件校验。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SideEffect(StrEnum):
    """工具副作用分级(_schema.json#/$defs/sideEffect)。"""

    read = "read"
    write = "write"
    assistant_write = "assistant_write"


class ErrorCode(StrEnum):
    """全局错误码(_schema.json#/$defs/errorCode;唯一事实源)。"""

    NO_PERMISSION = "NO_PERMISSION"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    TIMEOUT = "TIMEOUT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    AMBIGUOUS_FIELD = "AMBIGUOUS_FIELD"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    SANDBOX_VIOLATION = "SANDBOX_VIOLATION"
    UNSUPPORTED = "UNSUPPORTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_FORBID = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# ToolSpec(urn:zijin:toolspec)
# --------------------------------------------------------------------------- #
class ToolSpec(BaseModel):
    """单个工具契约。"""

    model_config = _FORBID

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permission_scope: str
    side_effects: SideEffect
    confirmation_required: bool
    timeout_ms: int
    errors: list[ErrorCode]
    enabled_by_default: bool = True
    version: str = "0.1.0"


@dataclass(frozen=True)
class LoadedToolSpec:
    """加载后的工具规格 + 加载元数据(domain 由目录/名称派生,非契约字段)。"""

    spec: ToolSpec
    domain: str
    path: Path


# --------------------------------------------------------------------------- #
# 调用信封(urn:zijin:envelope)
# --------------------------------------------------------------------------- #
class UserCtx(BaseModel):
    """零信任身份上下文(envelope#/$defs/userCtx,红线 3)。"""

    model_config = _FORBID

    tenant_id: str
    user_id: str
    roles: list[str]
    data_scope: dict[str, Any]
    permissions: list[str] = Field(default_factory=list)


class Confirmation(BaseModel):
    """写工具的二次确认凭据(红线 4 第二闸)。"""

    model_config = _FORBID

    confirmed: bool
    token: str


class ToolInvocation(BaseModel):
    """工具调用信封;user_ctx 必含(红线 3)。"""

    model_config = _FORBID

    trace_id: str
    tool: str
    args: dict[str, Any]
    user_ctx: UserCtx
    confirmation: Confirmation | None = None
    ts: str | None = None


# --------------------------------------------------------------------------- #
# AgentState(urn:zijin:agent-state,方案 §4.2)
# --------------------------------------------------------------------------- #
class AgentMode(StrEnum):
    react = "react"
    plan_execute = "plan_execute"


class StepStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    failed = "failed"
    skipped = "skipped"


class CapabilityHint(StrEnum):
    rag = "rag"
    data = "data"
    code = "code"
    sop = "sop"
    base = "base"


class WorkspaceItemType(StrEnum):
    sql_result = "sql_result"
    code_evidence = "code_evidence"
    doc_chunks = "doc_chunks"
    sop_run = "sop_run"


class AgentIds(BaseModel):
    model_config = _FORBID

    session_id: str
    trace_id: str
    tenant_id: str
    user_id: str


class AgentUserCtx(BaseModel):
    """AgentState 内的 user_ctx(tenant_id/user_id 在 ids 中)。"""

    model_config = _FORBID

    roles: list[str]
    data_scope: dict[str, Any]
    permissions: list[str] = Field(default_factory=list)


class Step(BaseModel):
    model_config = _FORBID

    id: str
    goal: str
    status: StepStatus
    capability_hint: CapabilityHint | None = None
    depends_on: list[str] = Field(default_factory=list)
    needs_confirmation: bool = False


class Plan(BaseModel):
    model_config = _FORBID

    version: int
    steps: list[Step]


class WorkspaceItem(BaseModel):
    model_config = _FORBID

    key: str
    type: WorkspaceItemType
    ref: str
    summary: str


class Workspace(BaseModel):
    model_config = _FORBID

    items: list[WorkspaceItem] = Field(default_factory=list)


class Budget(BaseModel):
    model_config = _FORBID

    max_steps: int
    max_cost: float
    used_steps: int
    used_cost: float


class Reflection(BaseModel):
    model_config = _FORBID

    inline_retries: int
    verdicts: list[dict[str, Any]] = Field(default_factory=list)


class AgentState(BaseModel):
    model_config = _FORBID

    ids: AgentIds
    user_ctx: AgentUserCtx
    mode: AgentMode
    messages: list[dict[str, Any]]
    plan: Plan
    workspace: Workspace
    budget: Budget
    reflection: Reflection
    scratchpad: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 审计事件(urn:zijin:audit,§9.2)
# --------------------------------------------------------------------------- #
class ResultStatus(StrEnum):
    ok = "ok"
    error = "error"
    denied = "denied"
    timeout = "timeout"


class AuditWho(BaseModel):
    model_config = _FORBID

    tenant_id: str
    user_id: str
    roles: list[str]


class AuditEvent(BaseModel):
    model_config = _FORBID

    who: AuditWho
    tool: str
    args_digest: str
    result_status: ResultStatus
    trace_id: str
    ts: str
    error_code: ErrorCode | None = None
    latency_ms: int | None = None


# --------------------------------------------------------------------------- #
# SOP 资产(urn:zijin:sop,附录 B);深层结构用 dict 承载,真相在 _schema.yaml
# --------------------------------------------------------------------------- #
class SopSideEffect(StrEnum):
    read = "read"
    write = "write"


class Sop(BaseModel):
    model_config = _FORBID

    id: str
    name: str
    description: str
    preconditions: dict[str, Any]
    inputs: list[dict[str, Any]]
    postconditions: dict[str, Any]
    on_failure: list[dict[str, Any]]
    meta: dict[str, Any]
    aliases: list[str] = Field(default_factory=list)
    domain: str | None = None
    side_effects: SopSideEffect | None = None
    requires_confirmation: bool | None = None
    entry: dict[str, Any] | None = None
    api: dict[str, Any] | None = None
    ui: dict[str, Any] | None = None
