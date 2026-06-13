"""contracts —— 框架无关的契约层(CLAUDE.md §5)。

schema 文件(contracts/*.json|yaml)是唯一事实源;本包提供 pydantic 运行时模型、
加载器与校验器,供各服务对着契约实现。
"""

from __future__ import annotations

from .loader import (
    iter_toolspec_paths,
    load_schema,
    load_toolspecs,
)
from .models import (
    AgentState,
    AuditEvent,
    Confirmation,
    ErrorCode,
    LoadedToolSpec,
    SideEffect,
    Sop,
    ToolInvocation,
    ToolSpec,
    UserCtx,
)
from .validator import (
    ContractValidationError,
    validate_agent_state,
    validate_audit,
    validate_envelope,
    validate_sop,
    validate_toolspec,
)

__version__ = "0.1.0"

__all__ = [
    "AgentState",
    "AuditEvent",
    "Confirmation",
    "ContractValidationError",
    "ErrorCode",
    "LoadedToolSpec",
    "SideEffect",
    "Sop",
    "ToolInvocation",
    "ToolSpec",
    "UserCtx",
    "iter_toolspec_paths",
    "load_schema",
    "load_toolspecs",
    "validate_agent_state",
    "validate_audit",
    "validate_envelope",
    "validate_sop",
    "validate_toolspec",
]
