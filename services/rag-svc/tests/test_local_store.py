"""LocalKnowledgeStore:检索前 ACL 过滤(受限 chunk 不入候选)+ 相关性排序 + 删除清理持久化。"""

from __future__ import annotations

from pathlib import Path

from llm import HashingEmbedder
from rag_svc import LocalKnowledgeStore
from rag_svc.models import Chunk


def _chunk(chunk_id: str, text: str, tags: list[str], doc_id: str = "d") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
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


async def test_remove_doc_and_file_hash_persist(tmp_path: Path) -> None:
    """删除文档:remove_doc + remove_file_hash 清理后 save→load,不留残留(删除端点依赖)。"""
    path = tmp_path / "index.json"
    store = LocalKnowledgeStore(embedder=HashingEmbedder())
    await store.insert([_chunk("c1", "资金计划执行率", ["public"], doc_id="business:a.md")])
    store.set_file_hash("a.md", "h1")
    store.save(path)

    loaded = LocalKnowledgeStore.load(path, embedder=HashingEmbedder())
    assert loaded.chunk_count() == 1
    assert loaded.file_hash("a.md") == "h1"
    loaded.remove_doc("business:a.md")
    loaded.remove_file_hash("a.md")
    loaded.save(path)

    again = LocalKnowledgeStore.load(path, embedder=HashingEmbedder())
    assert again.chunk_count() == 0
    assert again.file_hash("a.md") is None


def test_remove_file_hash_missing_noop() -> None:
    store = LocalKnowledgeStore(embedder=HashingEmbedder())
    store.remove_file_hash("nope.md")  # 不存在键 → no-op 不抛
    assert store.file_hash("nope.md") is None
