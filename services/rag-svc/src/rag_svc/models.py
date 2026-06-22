"""知识库 RAG 运行时模型(方案 §5.3)。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_FORBID = ConfigDict(extra="forbid")


class Chunk(BaseModel):
    """一个检索单元:正文 + 来源/位置/ACL 元数据 + 向量。"""

    model_config = _FORBID

    chunk_id: str
    doc_id: str
    kb: str
    source: str
    location: str
    text: str
    acl_tags: list[str] = Field(default_factory=list)
    tenant_id: str | None = None  # 租户私有内容归属;None=全局知识(对所有租户可见,红线 9)
    version: str = "0"
    effective_date: str | None = None
    embedding: list[float] = Field(default_factory=list)


class Citation(BaseModel):
    model_config = _FORBID

    source: str
    location: str


class RetrievedChunk(BaseModel):
    model_config = _FORBID

    chunk: Chunk
    score: float


class SearchResult(BaseModel):
    model_config = _FORBID

    summary: str
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


# ── 知识图谱(LightRAG 图查询;映射见 graph.py + docs/integration/knowledge-graph-api.md)──
# 字段对应 LightRAG 真实可得项。LightRAG 图原生无 tenant_id/acl_tags(provenance 仅
# source_id/file_path),故此二字段供 rag-svc 内 ACL 过滤(Mock 自带;真实路径靠分库,见 graph.py)。
class GraphNode(BaseModel):
    model_config = _FORBID

    entity_id: str  # LightRAG 节点 id(= 实体名)
    name: str  # 展示名(LightRAG 无独立展示名,= entity_id)
    entity_type: str | None = None  # = labels[0] / properties.entity_type
    description: str | None = None  # = properties.description
    source: str | None = None  # 源文档 = properties.file_path(可能缺省)
    degree: int | None = None  # 连接度(best-effort:由返回子图入射边计;非全局精确值)
    chunk_ref: str | None = None  # = properties.source_id(LightRAG chunk ids)
    tenant_id: str | None = None  # 租户归属;None=全局(红线 9 过滤用)
    acl_tags: list[str] = Field(default_factory=list)  # ACL 标签(红线 5 过滤用)


class GraphEdge(BaseModel):
    model_config = _FORBID

    edge_id: str
    source_id: str  # 源节点 entity_id(= edge.source)
    target_id: str  # 目标节点 entity_id(= edge.target)
    relation_type: str | None = None  # = edge.type / properties.keywords
    description: str | None = None  # = properties.description
    source_doc: str | None = None  # = properties.file_path
    tenant_id: str | None = None
    acl_tags: list[str] = Field(default_factory=list)


class GraphStats(BaseModel):
    model_config = _FORBID

    total_nodes: int
    total_edges: int
    entity_types: list[str] = Field(default_factory=list)


class GraphData(BaseModel):
    model_config = _FORBID

    kb: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    stats: GraphStats
    is_truncated: bool = False  # 大图保护:超 max_nodes 截断(LightRAG is_truncated 口径)


class NodeDetail(BaseModel):
    model_config = _FORBID

    node: GraphNode | None = None  # 无权 / 不存在 → None
    neighbors: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class GraphSearchResult(BaseModel):
    model_config = _FORBID

    entities: list[GraphNode] = Field(default_factory=list)
    relations: list[GraphEdge] = Field(default_factory=list)
