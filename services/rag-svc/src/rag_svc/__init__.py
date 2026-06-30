"""rag-svc —— 知识库 RAG(双库 + 检索前 ACL 过滤 + 引用,方案 §5.3)。"""

from __future__ import annotations

from . import acl
from .graph import (
    KnowledgeGraphProvider,
    LightRagGraphProvider,
    MockGraphProvider,
    filter_graph,
    graph_read_dir,
    graph_working_dir,
)
from .lightrag_store import LightRagStore
from .models import (
    Chunk,
    Citation,
    GraphData,
    GraphEdge,
    GraphNode,
    GraphSearchResult,
    GraphStats,
    NodeDetail,
    RetrievedChunk,
    SearchResult,
)
from .service import RagService
from .store import KnowledgeStore, LocalKnowledgeStore

__version__ = "0.1.0"

__all__ = [
    "Chunk",
    "Citation",
    "GraphData",
    "GraphEdge",
    "GraphNode",
    "GraphSearchResult",
    "GraphStats",
    "KnowledgeGraphProvider",
    "KnowledgeStore",
    "LightRagGraphProvider",
    "LightRagStore",
    "LocalKnowledgeStore",
    "MockGraphProvider",
    "NodeDetail",
    "RagService",
    "RetrievedChunk",
    "SearchResult",
    "acl",
    "filter_graph",
    "graph_read_dir",
    "graph_working_dir",
]
