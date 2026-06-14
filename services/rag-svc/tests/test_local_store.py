"""LocalKnowledgeStore:检索前 ACL 过滤(受限 chunk 不入候选)+ 相关性排序。"""

from __future__ import annotations

from llm import HashingEmbedder
from rag_svc import LocalKnowledgeStore
from rag_svc.models import Chunk


def _chunk(chunk_id: str, text: str, tags: list[str]) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id="d",
        kb="business",
        source="s",
        location=chunk_id,
        text=text,
        acl_tags=tags,
    )


def _public_only(chunk: Chunk) -> bool:
    return "public" in chunk.acl_tags


def _all_visible(chunk: Chunk) -> bool:
    return True


async def test_acl_prefilter_excludes_restricted() -> None:
    store = LocalKnowledgeStore(embedder=HashingEmbedder())
    await store.insert(
        [
            _chunk("c1", "资金计划执行率 公开口径", ["public"]),
            _chunk("c2", "资金计划执行率 内部备注", ["internal"]),
        ]
    )
    ids = [r.chunk.chunk_id for r in await store.search("执行率", visible=_public_only, top_k=10)]
    assert "c1" in ids
    assert "c2" not in ids  # 红线 5:受限 chunk 不进候选/排序

    all_ids = {
        r.chunk.chunk_id for r in await store.search("执行率", visible=_all_visible, top_k=10)
    }
    assert {"c1", "c2"} <= all_ids


async def test_ranks_relevant_first() -> None:
    store = LocalKnowledgeStore(embedder=HashingEmbedder())
    await store.insert(
        [
            _chunk("rel", "资金计划执行率口径说明", ["public"]),
            _chunk("irr", "今天天气晴朗适合出游", ["public"]),
        ]
    )
    results = await store.search("执行率口径", visible=_all_visible, top_k=2)
    assert results[0].chunk.chunk_id == "rel"
