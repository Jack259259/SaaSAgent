"""search_knowledge handler:摘要+句柄、引用透出;无权 user_ctx 检索不到受限文档(红线 5/8)。"""

from __future__ import annotations

from collections.abc import Sequence

from contracts import UserCtx
from llm import HashingEmbedder
from orchestrator import ToolContext, Workspace
from orchestrator.tools import make_search_knowledge_handler
from rag_svc import LocalKnowledgeStore, RagService, acl
from rag_svc.models import Chunk


def _uc(roles: Sequence[str]) -> UserCtx:
    return UserCtx(tenant_id="t", user_id="u", roles=list(roles), data_scope={}, permissions=["*"])


async def _service() -> RagService:
    store = LocalKnowledgeStore(embedder=HashingEmbedder())
    await store.insert(
        [
            Chunk(
                chunk_id="b1",
                doc_id="d1",
                kb="business",
                source="业务手册/执行率公开",
                location="段落0",
                text="资金计划执行率口径说明",
                acl_tags=["public"],
            ),
            Chunk(
                chunk_id="b2",
                doc_id="d2",
                kb="business",
                source="内部备注/执行率",
                location="段落0",
                text="资金计划执行率内部稽核口径",
                acl_tags=["internal"],
            ),
        ]
    )
    empty = LocalKnowledgeStore(embedder=HashingEmbedder())
    return RagService(stores={acl.KB_BUSINESS: store, acl.KB_IT_DESIGN: empty})


async def test_handler_summary_handle_citations_and_acl() -> None:
    handler = make_search_knowledge_handler(await _service())
    workspace = Workspace()
    ctx = ToolContext(user_ctx=_uc(["tenant_user"]), workspace=workspace, trace_id="t")

    out = await handler({"question": "执行率口径", "kb": "business", "top_k": 5}, ctx)

    assert not out.is_error
    assert out.raw["chunks_ref"].startswith("ws://")  # 红线 8:摘要 + 句柄
    citations = out.raw["citations"]
    assert citations
    assert all("source" in c and "location" in c for c in citations)
    # 红线 5:tenant_user 无权,内部片段不出现在引用或句柄
    assert not any("内部" in c["source"] for c in citations)
    chunks = workspace.get(out.raw["chunks_ref"]).raw
    assert all("内部" not in item["chunk"]["source"] for item in chunks)
