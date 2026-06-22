"""知识图谱查询层:Provider 抽象 + Mock(CI)/ LightRag(生产)两实现 + ACL 过滤。

红线 5/9:节点/边的租户 ∧ 标签 ACL 过滤在 rag-svc 内完成(由 RagService 调 ``filter_graph``),
不靠上层兜底。

LightRAG 图原生**无 tenant_id/acl_tags**(provenance 仅 source_id/file_path,见
docs/integration/knowledge-upload.md),故 ACL 分层(强→弱):
  - **KB 级**:it_design 仅内部角色 —— 由 RagService 的 ``kb_allowed`` 在查图前拦截(§9.3 物理隔离)。
  - **租户级**:生产按 (kb, tenant) 分目录建图,Provider 按 tenant 选实例(选库即隔离,红线 9)。
  - **标签级**:best-effort —— file_path→acl_tags sidecar(缺则回退库默认);记 TODO。
``MockGraphProvider`` 的 fixture 自带 tenant_id/acl_tags,``filter_graph`` 真实生效且被单测覆盖
(与 LocalKnowledgeStore[可测] vs LightRagStore[真实/不进 CI] 的既定范式一致)。
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from contracts import UserCtx

from . import acl
from .models import GraphData, GraphEdge, GraphNode, GraphSearchResult, GraphStats, NodeDetail

if TYPE_CHECKING:
    from llm import Embedder, Provider

_KB_DEFAULT_TAG = {acl.KB_BUSINESS: "public", acl.KB_IT_DESIGN: "internal"}


# ── ACL 过滤(红线 5/9;在数据离开 rag-svc 前施加)──────────────────────────────────
def filter_graph(
    user_ctx: UserCtx, nodes: list[GraphNode], edges: list[GraphEdge]
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """移除无权节点;并移除任一端点被移除或自身无权的边(不经边泄露受限节点)。"""
    allowed_nodes = [
        n for n in nodes if acl.chunk_allowed(user_ctx, tenant_id=n.tenant_id, acl_tags=n.acl_tags)
    ]
    allowed_ids = {n.entity_id for n in allowed_nodes}
    allowed_edges = [
        e
        for e in edges
        if e.source_id in allowed_ids
        and e.target_id in allowed_ids
        and acl.chunk_allowed(user_ctx, tenant_id=e.tenant_id, acl_tags=e.acl_tags)
    ]
    return allowed_nodes, allowed_edges


def compute_stats(nodes: list[GraphNode], edges: list[GraphEdge]) -> GraphStats:
    types = sorted({n.entity_type for n in nodes if n.entity_type})
    return GraphStats(total_nodes=len(nodes), total_edges=len(edges), entity_types=types)


# ── Provider 抽象 ────────────────────────────────────────────────────────────────
class KnowledgeGraphProvider(Protocol):
    """返回**未经 ACL 过滤**的原始图;ACL 由 RagService 调 filter_graph 施加。

    tenant_id 入参用于真实 LightRAG 的 (kb, tenant) 分库物理选择;Mock 忽略之(过滤在 filter_graph)。
    """

    async def get_graph(
        self,
        kb: str,
        *,
        tenant_id: str | None,
        entity_types: list[str] | None,
        max_nodes: int,
        center_entity: str | None,
    ) -> GraphData: ...

    async def get_node(
        self, kb: str, entity_id: str, *, tenant_id: str | None, depth: int
    ) -> NodeDetail: ...

    async def search_nodes(
        self, kb: str, query: str, *, tenant_id: str | None, top_k: int, search_in: str
    ) -> GraphSearchResult: ...


# ── Mock 实现(虚构资金计划领域;CI/单测默认;严禁真实业务内容)─────────────────────
def _degrees(edges: list[GraphEdge]) -> dict[str, int]:
    deg: dict[str, int] = defaultdict(int)
    for e in edges:
        deg[e.source_id] += 1
        deg[e.target_id] += 1
    return deg


def _adjacency(edges: list[GraphEdge]) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        adj[e.source_id].add(e.target_id)
        adj[e.target_id].add(e.source_id)
    return adj


def _bfs(start: str, adj: dict[str, set[str]], depth: int) -> set[str]:
    seen = {start}
    frontier = {start}
    for _ in range(max(depth, 0)):
        nxt: set[str] = set()
        for node in frontier:
            nxt |= adj.get(node, set())
        nxt -= seen
        seen |= nxt
        frontier = nxt
        if not frontier:
            break
    return seen


class MockGraphProvider:
    """内存 fixture 图(business + it_design),节点/边带 tenant_id/acl_tags 供 ACL 真测。"""

    def __init__(self) -> None:
        self._nodes, self._edges = _build_fixture()

    def _kb(self, kb: str) -> tuple[list[GraphNode], list[GraphEdge]]:
        return list(self._nodes.get(kb, [])), list(self._edges.get(kb, []))

    def _with_degree(self, nodes: list[GraphNode], edges: list[GraphEdge]) -> list[GraphNode]:
        deg = _degrees(edges)
        return [n.model_copy(update={"degree": deg.get(n.entity_id, 0)}) for n in nodes]

    async def get_graph(
        self,
        kb: str,
        *,
        tenant_id: str | None,
        entity_types: list[str] | None,
        max_nodes: int,
        center_entity: str | None,
    ) -> GraphData:
        nodes, edges = self._kb(kb)
        nodes = self._with_degree(nodes, edges)
        if center_entity:  # 以该实体为中心的子图(默认 2 跳)
            keep = _bfs(center_entity, _adjacency(edges), depth=2)
            nodes = [n for n in nodes if n.entity_id in keep]
        if entity_types:
            wanted = set(entity_types)
            nodes = [n for n in nodes if n.entity_type in wanted]
        # 大图保护:按 degree 降序(同度按 entity_id 稳定)取 top-N(对齐 LightRAG node_label="*")。
        nodes.sort(key=lambda n: (-(n.degree or 0), n.entity_id))
        is_truncated = len(nodes) > max_nodes
        nodes = nodes[:max_nodes]
        kept = {n.entity_id for n in nodes}
        edges = [e for e in edges if e.source_id in kept and e.target_id in kept]
        return GraphData(
            kb=kb,
            nodes=nodes,
            edges=edges,
            stats=compute_stats(nodes, edges),
            is_truncated=is_truncated,
        )

    async def get_node(
        self, kb: str, entity_id: str, *, tenant_id: str | None, depth: int
    ) -> NodeDetail:
        nodes, edges = self._kb(kb)
        nodes = self._with_degree(nodes, edges)
        by_id = {n.entity_id: n for n in nodes}
        center = by_id.get(entity_id)
        if center is None:
            return NodeDetail(node=None, neighbors=[], edges=[])
        keep = _bfs(entity_id, _adjacency(edges), depth=depth)
        neighbors = [by_id[i] for i in keep if i != entity_id and i in by_id]
        sub_edges = [e for e in edges if e.source_id in keep and e.target_id in keep]
        return NodeDetail(node=center, neighbors=neighbors, edges=sub_edges)

    async def search_nodes(
        self, kb: str, query: str, *, tenant_id: str | None, top_k: int, search_in: str
    ) -> GraphSearchResult:
        nodes, edges = self._kb(kb)
        nodes = self._with_degree(nodes, edges)
        q = (query or "").strip().lower()

        def hit(n: GraphNode) -> bool:
            if not q:
                return False
            in_name = q in n.name.lower() or q in n.entity_id.lower()
            in_desc = n.description is not None and q in n.description.lower()
            if search_in == "name":
                return in_name
            if search_in == "description":
                return in_desc
            return in_name or in_desc  # both

        matched = sorted(
            (n for n in nodes if hit(n)), key=lambda n: (-(n.degree or 0), n.entity_id)
        )
        matched = matched[:top_k]
        ids = {n.entity_id for n in matched}
        relations = [e for e in edges if e.source_id in ids and e.target_id in ids]
        return GraphSearchResult(entities=matched, relations=relations)


def _build_fixture() -> tuple[dict[str, list[GraphNode]], dict[str, list[GraphEdge]]]:
    """虚构资金计划/IT 设计领域图(无真实业务内容)。business 含 internal/租户私有节点供 ACL 负例。"""

    def node(
        eid: str, etype: str, desc: str, *, tenant: str | None = None, tags: list[str]
    ) -> GraphNode:
        return GraphNode(
            entity_id=eid,
            name=eid,
            entity_type=etype,
            description=desc,
            source="fixture://知识库/示例文档",
            chunk_ref="fixture-chunk",
            tenant_id=tenant,
            acl_tags=tags,
        )

    def edge(
        src: str, tgt: str, rel: str, *, tenant: str | None = None, tags: list[str]
    ) -> GraphEdge:
        return GraphEdge(
            edge_id=f"{src}->{tgt}",
            source_id=src,
            target_id=tgt,
            relation_type=rel,
            description=f"{src} {rel} {tgt}",
            source_doc="fixture://知识库/示例文档",
            tenant_id=tenant,
            acl_tags=tags,
        )

    pub = ["public"]
    business_nodes = [
        node("资金计划", "概念", "企业对未来资金收支的预测与安排", tags=pub),
        node("执行率", "指标", "实际执行与计划的比率", tags=pub),
        node("现金流量表", "报表", "经营/投资/筹资现金流", tags=pub),
        node("滚动预测", "方法", "逐月滚动测算资金缺口", tags=pub),
        node("授信额度", "概念", "银行授予的可用融资额度", tags=pub),
        node("内部审计口径", "制度", "内部审计专用口径(仅内部)", tags=["internal"]),
        node("ACME专属调度", "方案", "ACME 租户专属资金调度", tenant="t_acme", tags=["tenant"]),
        node("他司预算", "方案", "其他租户预算(跨租户负例)", tenant="t_other", tags=["tenant"]),
    ]
    business_edges = [
        edge("资金计划", "执行率", "关联", tags=pub),
        edge("资金计划", "现金流量表", "包含", tags=pub),
        edge("资金计划", "滚动预测", "使用", tags=pub),
        edge("资金计划", "授信额度", "涉及", tags=pub),
        edge("执行率", "现金流量表", "体现", tags=pub),
        edge("滚动预测", "授信额度", "触发", tags=pub),
        edge("资金计划", "内部审计口径", "受约束", tags=["internal"]),
        edge("资金计划", "ACME专属调度", "定制", tenant="t_acme", tags=["tenant"]),
        edge("资金计划", "他司预算", "定制", tenant="t_other", tags=["tenant"]),
    ]
    # it_design 库:整库仅内部角色可查(kb_allowed 在 RagService 拦截);标签随库默认 internal。
    it_nodes = [
        node("对账服务设计", "设计", "资金对账服务的接口设计", tags=["internal"]),
        node("数据模型", "设计", "资金计划核心数据模型", tags=["internal"]),
    ]
    it_edges = [edge("对账服务设计", "数据模型", "依赖", tags=["internal"])]
    return (
        {acl.KB_BUSINESS: business_nodes, acl.KB_IT_DESIGN: it_nodes},
        {acl.KB_BUSINESS: business_edges, acl.KB_IT_DESIGN: it_edges},
    )


# ── LightRAG 实现(真实;不进 CI —— lightrag 未安装,镜像 LightRagStore 范式)──────────
class LightRagGraphProvider:
    """从真实 LightRAG 图提取 nodes/edges。

    - 经 ``rag.get_knowledge_graph(node_label, max_depth, max_nodes)``(node_label="*"=全图,按
      degree 取 top-N)/ ``chunk_entity_relation_graph.search_labels``;LLM/embedding 经 packages/llm
      网关(图读取本身不触发 LLM,但实例构造仍走网关,不直连厂商 SDK)。
    - **租户物理隔离**:``working_dir_resolver(kb, tenant)`` 选 (kb, tenant) 图目录(+ 全局图)。
    - acl_tags **best-effort**:回退库默认(business→public,it_design→internal);精确标签需
      file_path→tag sidecar(待 LightRagStore.insert 写 file_path)。tenant_id 取分库 tenant。
    """

    def __init__(
        self,
        *,
        working_dir_resolver: Any,
        embedder: Embedder,
        provider: Provider,
    ) -> None:
        self._resolve = working_dir_resolver
        self._embedder = embedder
        self._provider = provider
        self._cache: dict[tuple[str, str], Any] = {}

    async def _rag(self, kb: str, tenant_id: str | None) -> Any:  # pragma: no cover — 生产路径
        from .lightrag_store import LightRagStore

        key = (kb, tenant_id or "_global")
        store = self._cache.get(key)
        if store is None:
            working_dir = Path(self._resolve(kb, tenant_id))
            store = LightRagStore(
                working_dir=working_dir, embedder=self._embedder, provider=self._provider
            )
            self._cache[key] = store
        return await store._ensure()  # 复用 LightRagStore 的网关构造(embedding/llm 经网关)

    def _tags_for(self, kb: str, _file_path: str | None) -> list[str]:
        # best-effort:回退库默认;TODO 接 file_path→acl_tags sidecar。
        return [_KB_DEFAULT_TAG.get(kb, "public")]

    def _node(self, kb: str, tenant_id: str | None, raw: Any, degree: int | None) -> GraphNode:
        props = dict(getattr(raw, "properties", {}) or {})
        labels = list(getattr(raw, "labels", []) or [])
        file_path = props.get("file_path")
        return GraphNode(
            entity_id=str(raw.id),
            name=str(props.get("entity_id") or raw.id),
            entity_type=(labels[0] if labels else props.get("entity_type")),
            description=props.get("description"),
            source=file_path,
            degree=degree,
            chunk_ref=props.get("source_id"),
            tenant_id=tenant_id,
            acl_tags=self._tags_for(kb, file_path),
        )

    def _edge(self, kb: str, tenant_id: str | None, raw: Any) -> GraphEdge:
        props = dict(getattr(raw, "properties", {}) or {})
        return GraphEdge(
            edge_id=str(getattr(raw, "id", f"{raw.source}->{raw.target}")),
            source_id=str(raw.source),
            target_id=str(raw.target),
            relation_type=getattr(raw, "type", None) or props.get("keywords"),
            description=props.get("description"),
            source_doc=props.get("file_path"),
            tenant_id=tenant_id,
            acl_tags=self._tags_for(kb, props.get("file_path")),
        )

    async def get_graph(
        self,
        kb: str,
        *,
        tenant_id: str | None,
        entity_types: list[str] | None,
        max_nodes: int,
        center_entity: str | None,
    ) -> GraphData:  # pragma: no cover — 生产路径
        rag = await self._rag(kb, tenant_id)
        kg = await rag.get_knowledge_graph(
            node_label=center_entity or "*", max_depth=2, max_nodes=max_nodes
        )
        deg = _degrees(
            [
                GraphEdge(edge_id="-", source_id=str(e.source), target_id=str(e.target))
                for e in kg.edges
            ]
        )
        nodes = [self._node(kb, tenant_id, n, deg.get(str(n.id))) for n in kg.nodes]
        if entity_types:
            wanted = set(entity_types)
            nodes = [n for n in nodes if n.entity_type in wanted]
        kept = {n.entity_id for n in nodes}
        edges = [
            self._edge(kb, tenant_id, e)
            for e in kg.edges
            if str(e.source) in kept and str(e.target) in kept
        ]
        return GraphData(
            kb=kb,
            nodes=nodes,
            edges=edges,
            stats=compute_stats(nodes, edges),
            is_truncated=bool(getattr(kg, "is_truncated", False)),
        )

    async def get_node(
        self, kb: str, entity_id: str, *, tenant_id: str | None, depth: int
    ) -> NodeDetail:  # pragma: no cover — 生产路径
        rag = await self._rag(kb, tenant_id)
        kg = await rag.get_knowledge_graph(node_label=entity_id, max_depth=depth, max_nodes=1000)
        deg = _degrees(
            [
                GraphEdge(edge_id="-", source_id=str(e.source), target_id=str(e.target))
                for e in kg.edges
            ]
        )
        center: GraphNode | None = None
        neighbors: list[GraphNode] = []
        for n in kg.nodes:
            gn = self._node(kb, tenant_id, n, deg.get(str(n.id)))
            if gn.entity_id == entity_id:
                center = gn
            else:
                neighbors.append(gn)
        edges = [self._edge(kb, tenant_id, e) for e in kg.edges]
        return NodeDetail(node=center, neighbors=neighbors, edges=edges)

    async def search_nodes(
        self, kb: str, query: str, *, tenant_id: str | None, top_k: int, search_in: str
    ) -> GraphSearchResult:  # pragma: no cover — 生产路径
        rag = await self._rag(kb, tenant_id)
        labels = await rag.chunk_entity_relation_graph.search_labels(query, limit=top_k)
        entities: list[GraphNode] = []
        for label in labels[:top_k]:
            raw = await rag.chunk_entity_relation_graph.get_node(label)
            if raw is None:
                continue
            props = dict(raw)
            entities.append(
                GraphNode(
                    entity_id=str(label),
                    name=str(props.get("entity_id") or label),
                    entity_type=props.get("entity_type"),
                    description=props.get("description"),
                    source=props.get("file_path"),
                    chunk_ref=props.get("source_id"),
                    tenant_id=tenant_id,
                    acl_tags=self._tags_for(kb, props.get("file_path")),
                )
            )
        return GraphSearchResult(entities=entities, relations=[])
