"""orchestrator —— 自研薄编排循环(CLAUDE.md §3 / 方案 §4、§11.1)。"""

from __future__ import annotations

from .audit import anonymous_who, digest_args, emit_audit, who_from_user_ctx
from .compaction import Compactor, TruncationCompactor
from .events import (
    AnswerDeltaEvent,
    AskUserEvent,
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
from .reflection import Verdict, Verifier, VerifierRegistry, default_output_schema_verifier
from .registry import ToolHandler, ToolNotFoundError, ToolOutcome, ToolRegistry
from .session import (
    Pending,
    Session,
    SessionAccessError,
    SessionNotFoundError,
    SessionStore,
)
from .system_prompt import build_system_prompt
from .tool_context import ToolContext
from .tools import base_tool_handlers
from .workspace import Workspace, WorkspaceItem, WorkspacePage

__version__ = "0.1.0"

__all__ = [
    "AnswerDeltaEvent",
    "AskUserEvent",
    "Budget",
    "Compactor",
    "ConfirmRequestEvent",
    "DefaultPermissionChecker",
    "DoneEvent",
    "ErrorEvent",
    "NoPermissionError",
    "Orchestrator",
    "OrchestratorEvent",
    "Pending",
    "PermissionChecker",
    "PlanEvent",
    "Session",
    "SessionAccessError",
    "SessionNotFoundError",
    "SessionStore",
    "StepEvent",
    "ToolCallEvent",
    "ToolContext",
    "ToolHandler",
    "ToolNotFoundError",
    "ToolOutcome",
    "ToolRegistry",
    "ToolResultSummaryEvent",
    "TruncationCompactor",
    "Verdict",
    "Verifier",
    "VerifierRegistry",
    "Workspace",
    "WorkspaceItem",
    "WorkspacePage",
    "anonymous_who",
    "assert_user_ctx",
    "base_tool_handlers",
    "build_system_prompt",
    "default_output_schema_verifier",
    "digest_args",
    "emit_audit",
    "who_from_user_ctx",
]
