"""save_memory / search_memory 工具 handler(§7;红线 4 助手域写 + 审计)。

save_memory:画像类直写(契约 scope=profile/preference/glossary,结构上即禁经验直写);
经验仅 reflection-worker 经 MemoryService.record_experience 录入(非工具路径)。
"""

from __future__ import annotations

from typing import Any

import structlog

from memory_svc import MemoryKind, MemoryService

from ..registry import ToolHandler, ToolOutcome
from ..tool_context import ToolContext

_log = structlog.get_logger("orchestrator.tools.memory")


def make_save_memory_handler(memory_service: MemoryService) -> ToolHandler:
    async def save_memory(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        content = str(args.get("content", ""))
        scope = str(args.get("scope") or "profile")
        importance = float(args.get("importance", 0.5))
        result = await memory_service.save_profile(
            ctx.user_ctx, content, scope=scope, importance=importance
        )
        # 助手域写审计(红线 4):谁/何范围/是否入库;不记原文明细。
        _log.info(
            "save_memory",
            scope=scope,
            stored=result.stored,
            tenant_id=ctx.user_ctx.tenant_id,
            user_id=ctx.user_ctx.user_id,
            trace_id=ctx.trace_id,
        )
        return ToolOutcome(
            summary="已记住该偏好" if result.stored else "未达写入门槛,未记录",
            raw={"memory_id": result.memory_id, "stored": result.stored},
        )

    return save_memory


def make_search_memory_handler(memory_service: MemoryService) -> ToolHandler:
    async def search_memory(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        raw_kinds = args.get("kinds")
        kinds = [MemoryKind(str(k)) for k in raw_kinds] if raw_kinds else None
        hits = await memory_service.search_memory(
            ctx.user_ctx, str(args.get("query", "")), kinds=kinds, top_k=int(args.get("top_k", 5))
        )
        return ToolOutcome(
            summary=f"命中 {len(hits)} 条记忆", raw={"results": [h.model_dump() for h in hits]}
        )

    return search_memory
