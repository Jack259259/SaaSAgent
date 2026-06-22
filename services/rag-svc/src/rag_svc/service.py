"""RagService:双知识库 + 检索前 ACL + 引用组装(方案 §5.3)。"""

from __future__ import annotations

from pathlib import Path

from contracts import UserCtx
from llm import Embedder, HashingEmbedder

from . import acl
from .graph import KnowledgeGraphProvider, compute_stats, filter_graph
from .models import (
    Chunk,
    Citation,
    GraphData,
    GraphSearchResult,
    GraphStats,
    NodeDetail,
    RetrievedChunk,
    SearchResult,
)
from .store import KnowledgeStore, LocalKnowledgeStore

_NO_EVIDENCE = "未在知识库中找到依据。"


def _empty_graph(kb: str) -> GraphData:
    return GraphData(
        kb=kb,
        nodes=[],
        edges=[],
        stats=GraphStats(total_nodes=0, total_edges=0),
        is_truncated=False,
    )


class RagService:
    def __init__(
        self,
        *,
        stores: dict[str, KnowledgeStore],
        graph_provider: KnowledgeGraphProvider | None = None,
    ) -> None:
        self._stores = stores
        self._graph = graph_provider

    @classmethod
    def from_dir(
        cls,
        base_dir: Path,
        *,
        embedder: Embedder | None = None,
        graph_provider: KnowledgeGraphProvider | None = None,
    ) -> RagService:
        emb = embedder or HashingEmbedder()
        stores: dict[str, KnowledgeStore] = {
            kb: LocalKnowledgeStore.load(base_dir / kb / "index.json", embedder=emb)
            for kb in (acl.KB_BUSINESS, acl.KB_IT_DESIGN)
        }
        return cls(stores=stores, graph_provider=graph_provider)

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

    # ── 知识图谱查询(只读;ACL 与 search_knowledge 同口径,首参 user_ctx)──────────────
    # kb_allowed 在查图前拦截(it_design 仅内部,§9.3);节点/边经 filter_graph 二次过滤(红线 5/9)。
    async def get_graph(
        self,
        user_ctx: UserCtx,
        kb: str,
        *,
        entity_types: list[str] | None = None,
        max_nodes: int = 200,
        center_entity: str | None = None,
    ) -> GraphData:
        if self._graph is None or not acl.kb_allowed(user_ctx, kb):
            return _empty_graph(kb)
        raw = await self._graph.get_graph(
            kb,
            tenant_id=user_ctx.tenant_id,
            entity_types=entity_types,
            max_nodes=max_nodes,
            center_entity=center_entity,
        )
        nodes, edges = filter_graph(user_ctx, raw.nodes, raw.edges)
        return GraphData(
            kb=kb,
            nodes=nodes,
            edges=edges,
            stats=compute_stats(nodes, edges),
            is_truncated=raw.is_truncated,
        )

    async def get_node(
        self, user_ctx: UserCtx, kb: str, entity_id: str, *, depth: int = 1
    ) -> NodeDetail:
        if self._graph is None or not acl.kb_allowed(user_ctx, kb):
            return NodeDetail(node=None, neighbors=[], edges=[])
        raw = await self._graph.get_node(kb, entity_id, tenant_id=user_ctx.tenant_id, depth=depth)
        if raw.node is None:
            return NodeDetail(node=None, neighbors=[], edges=[])
        nodes, edges = filter_graph(user_ctx, [raw.node, *raw.neighbors], raw.edges)
        kept = {n.entity_id for n in nodes}
        if entity_id not in kept:  # 无权看中心节点本身 → 视为不可见
            return NodeDetail(node=None, neighbors=[], edges=[])
        center = next(n for n in nodes if n.entity_id == entity_id)
        neighbors = [n for n in nodes if n.entity_id != entity_id]
        return NodeDetail(node=center, neighbors=neighbors, edges=edges)

    async def search_graph_nodes(
        self, user_ctx: UserCtx, kb: str, query: str, *, top_k: int = 10, search_in: str = "name"
    ) -> GraphSearchResult:
        if self._graph is None or not acl.kb_allowed(user_ctx, kb):
            return GraphSearchResult(entities=[], relations=[])
        raw = await self._graph.search_nodes(
            kb, query, tenant_id=user_ctx.tenant_id, top_k=top_k, search_in=search_in
        )
        entities, relations = filter_graph(user_ctx, raw.entities, raw.relations)
        return GraphSearchResult(entities=entities, relations=relations)
