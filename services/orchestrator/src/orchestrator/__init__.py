"""orchestrator —— 自研薄编排循环(CLAUDE.md §3 / 方案 §4、§11.1)。"""

from __future__ import annotations

from .audit import anonymous_who, digest_args, emit_audit, who_from_user_ctx
from .compaction import Compactor, TruncationCompactor
from .events import (
    AnswerDeltaEvent,
    ConfirmRequestEvent,
    DoneEvent,
    ErrorEvent,
    OrchestratorEvent,
    PlanEvent,
    StepEvent,
    ToolCallEvent,
    ToolResultSummaryEvent,
)
from .loop import Budget, Orchestrator
from .permissions import (
    DefaultPermissionChecker,
    NoPermissionError,
    PermissionChecker,
    assert_user_ctx,
)
from .registry import ToolHandler, ToolNotFoundError, ToolOutcome, ToolRegistry
from .system_prompt import build_system_prompt
from .workspace import Workspace, WorkspaceItem, WorkspacePage

__version__ = "0.1.0"

__all__ = [
    "AnswerDeltaEvent",
    "Budget",
    "Compactor",
    "ConfirmRequestEvent",
    "DefaultPermissionChecker",
    "DoneEvent",
    "ErrorEvent",
    "NoPermissionError",
    "Orchestrator",
    "OrchestratorEvent",
    "PermissionChecker",
    "PlanEvent",
    "StepEvent",
    "ToolCallEvent",
    "ToolHandler",
    "ToolNotFoundError",
    "ToolOutcome",
    "ToolRegistry",
    "ToolResultSummaryEvent",
    "TruncationCompactor",
    "Workspace",
    "WorkspaceItem",
    "WorkspacePage",
    "anonymous_who",
    "assert_user_ctx",
    "build_system_prompt",
    "digest_args",
    "emit_audit",
    "who_from_user_ctx",
]
