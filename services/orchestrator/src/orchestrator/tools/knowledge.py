"""search_knowledge 工具 handler(§5.3)。

适配工具契约 ↔ RagService:检索前 ACL 过滤由 RagService 负责(红线 5);结果"摘要 + 工作区句柄"
(红线 8),引用结构原样透出。
"""

from __future__ import annotations

from typing import Any

from rag_svc import RagService

from ..registry import ToolHandler, ToolOutcome
from ..tool_context import ToolContext


def make_search_knowledge_handler(rag_service: RagService) -> ToolHandler:
    async def search_knowledge(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        question = str(args.get("question", ""))
        kb_arg = args.get("kb")
        top_k = int(args.get("top_k", 5))
        result = await rag_service.search_knowledge(
            ctx.user_ctx, question, kb=str(kb_arg) if kb_arg else None, top_k=top_k
        )
        chunks_payload = [r.model_dump() for r in result.chunks]
        chunks_ref = ctx.workspace.put(
            key="knowledge/chunks", type="doc_chunks", summary=result.summary, raw=chunks_payload
        )
        return ToolOutcome(
            summary=result.summary,
            raw={
                "summary": result.summary,
                "chunks_ref": chunks_ref,
                "citations": [c.model_dump() for c in result.citations],
            },
        )

    return search_knowledge
