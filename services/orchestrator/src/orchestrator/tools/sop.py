"""find_sop / run_sop 工具 handler(§5.4 / 红线 4)。

run_sop:提交执行 → 命中 confirm 步则返回 ToolConfirmation(编排器暂停发 confirm_request);
resume 续行(双闸第二闸在 executor 内复验)。结果"摘要 + 报告句柄"(红线 8);审计 SOP/run/状态。
"""

from __future__ import annotations

from typing import Any

import structlog

from sop_executor import RunAccessError, RunState, RunStatus, SopService

from ..registry import ResumeHandler, ToolConfirmation, ToolHandler, ToolOutcome
from ..tool_context import ToolContext

_log = structlog.get_logger("orchestrator.tools.sop")


def make_find_sop_handler(sop_service: SopService) -> ToolHandler:
    async def find_sop(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        matches = sop_service.find_sop(str(args.get("query", "")), top_k=int(args.get("top_k", 5)))
        return ToolOutcome(
            summary=f"找到 {len(matches)} 个 SOP",
            raw={"matches": [m.model_dump() for m in matches]},
        )

    return find_sop


def _outcome(sop_service: SopService, state: RunState, ctx: ToolContext) -> ToolOutcome:
    if state.status == RunStatus.paused and state.pending_confirm is not None:
        return ToolOutcome(
            summary=f"待确认:{state.pending_confirm.prompt}({state.pending_confirm.action_preview})",
            raw={"run_id": state.run_id, "status": state.status.value},
            confirmation=ToolConfirmation(token=state.run_id, prompt=state.pending_confirm.prompt),
        )
    report = sop_service.report(state)
    report_ref = ctx.workspace.put(
        key="sop/report",
        type="sop_report",
        summary=report.message,
        raw=report.model_dump(mode="json"),
    )
    _log.info(
        "sop_run",
        sop_id=state.sop_id,
        run_id=state.run_id,
        status=state.status.value,
        steps=len(state.steps),
        tenant_id=ctx.user_ctx.tenant_id,
        user_id=ctx.user_ctx.user_id,
        trace_id=ctx.trace_id,
    )
    return ToolOutcome(
        summary=report.message,
        raw={"run_id": state.run_id, "status": state.status.value, "report_ref": report_ref},
        is_error=state.status == RunStatus.failed,
    )


def make_run_sop_handler(sop_service: SopService) -> tuple[ToolHandler, ResumeHandler]:
    async def run_sop(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        sop_id = str(args.get("sop_id", ""))
        try:
            state = await sop_service.submit(sop_id, dict(args.get("inputs") or {}), ctx.user_ctx)
        except KeyError:
            return ToolOutcome(summary=f"未找到 SOP:{sop_id}", is_error=True)
        return _outcome(sop_service, state, ctx)

    async def resume(token: str, confirmed: bool, ctx: ToolContext) -> ToolOutcome:
        try:
            state = await sop_service.resume(token, confirmed=confirmed, user_ctx=ctx.user_ctx)
        except KeyError:
            return ToolOutcome(summary="运行实例不存在或已过期", is_error=True)
        except RunAccessError:
            return ToolOutcome(summary="无权恢复该运行实例(归属校验未通过)", is_error=True)
        return _outcome(sop_service, state, ctx)

    return run_sop, resume
