"""编排器对外事件(经网关编码为 SSE)。字段须稳定,见 docs/dev/sse-protocol.md。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True)
class PlanEvent:
    version: int
    steps: list[dict[str, Any]]
    SSE_TYPE: ClassVar[str] = "plan"

    def data(self) -> dict[str, Any]:
        return {"version": self.version, "steps": self.steps}


@dataclass(frozen=True)
class StepEvent:
    index: int
    note: str
    SSE_TYPE: ClassVar[str] = "step"

    def data(self) -> dict[str, Any]:
        return {"index": self.index, "note": self.note}


@dataclass(frozen=True)
class ToolCallEvent:
    id: str
    tool: str
    arguments: dict[str, Any]
    SSE_TYPE: ClassVar[str] = "tool_call"

    def data(self) -> dict[str, Any]:
        return {"id": self.id, "tool": self.tool, "arguments": self.arguments}


@dataclass(frozen=True)
class ToolResultSummaryEvent:
    id: str
    tool: str
    summary: str
    workspace_ref: str
    SSE_TYPE: ClassVar[str] = "tool_result_summary"

    def data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "summary": self.summary,
            "workspace_ref": self.workspace_ref,
        }


@dataclass(frozen=True)
class ConfirmRequestEvent:
    """写操作确认暂停(阶段 3 实现;此处仅定义字段)。"""

    id: str
    prompt: str
    options: list[str] = field(default_factory=list)
    SSE_TYPE: ClassVar[str] = "confirm_request"

    def data(self) -> dict[str, Any]:
        return {"id": self.id, "prompt": self.prompt, "options": self.options}


@dataclass(frozen=True)
class AnswerDeltaEvent:
    text: str
    SSE_TYPE: ClassVar[str] = "answer_delta"

    def data(self) -> dict[str, Any]:
        return {"text": self.text}


@dataclass(frozen=True)
class DoneEvent:
    stop_reason: str
    used_steps: int
    SSE_TYPE: ClassVar[str] = "done"

    def data(self) -> dict[str, Any]:
        return {"stop_reason": self.stop_reason, "used_steps": self.used_steps}


@dataclass(frozen=True)
class ErrorEvent:
    code: str
    message: str
    SSE_TYPE: ClassVar[str] = "error"

    def data(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


OrchestratorEvent = (
    PlanEvent
    | StepEvent
    | ToolCallEvent
    | ToolResultSummaryEvent
    | ConfirmRequestEvent
    | AnswerDeltaEvent
    | DoneEvent
    | ErrorEvent
)
