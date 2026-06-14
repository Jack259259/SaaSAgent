"""RagService:双知识库 + 检索前 ACL + 引用组装(方案 §5.3)。"""

from __future__ import annotations

from pathlib import Path

from contracts import UserCtx
from llm import Embedder, HashingEmbedder

from . import acl
from .models import Chunk, Citation, RetrievedChunk, SearchResult
from .store import KnowledgeStore, LocalKnowledgeStore

_NO_EVIDENCE = "未在知识库中找到依据。"


class RagService:
    def __init__(self, *, stores: dict[str, KnowledgeStore]) -> None:
        self._stores = stores

    @classmethod
    def from_dir(cls, base_dir: Path, *, embedder: Embedder | None = None) -> RagService:
        emb = embedder or HashingEmbedder()
        stores: dict[str, KnowledgeStore] = {
            kb: LocalKnowledgeStore.load(base_dir / kb / "index.json", embedder=emb)
            for kb in (acl.KB_BUSINESS, acl.KB_IT_DESIGN)
        }
        return cls(stores=stores)

    async def search_knowledge(
        self, user_ctx: UserCtx, question: str, *, kb: str | None = None, top_k: int = 5
    ) -> SearchResult:
        target_kbs = [kb] if kb is not None else list(self._stores)

        def visible(chunk: Chunk) -> bool:
            # 红线 5+9:租户维度 ∧ 标签维度,均在检索前候选阶段施加。
            return acl.chunk_allowed(user_ctx, tenant_id=chunk.tenant_id, acl_tags=chunk.acl_tags)

        results: list[RetrievedChunk] = []
        for target in target_kbs:
            store = self._stores.get(target)
            if store is None or not acl.kb_allowed(user_ctx, target):
                continue  # 无权库根本不查(§9.3 物理隔离)
            results.extend(await store.search(question, visible=visible, top_k=top_k))

        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:top_k]
        if not results:
            return SearchResult(summary=_NO_EVIDENCE, chunks=[], citations=[])

        citations = [Citation(source=r.chunk.source, location=r.chunk.location) for r in results]
        sources = "; ".join(dict.fromkeys(r.chunk.source for r in results[:3]))
        return SearchResult(
            summary=f"命中 {len(results)} 条片段(来源:{sources})",
            chunks=results,
            citations=citations,
        )
