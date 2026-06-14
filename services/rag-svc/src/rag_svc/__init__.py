"""rag-svc —— 知识库 RAG(双库 + 检索前 ACL 过滤 + 引用,方案 §5.3)。"""

from __future__ import annotations

from . import acl
from .lightrag_store import LightRagStore
from .models import Chunk, Citation, RetrievedChunk, SearchResult
from .service import RagService
from .store import KnowledgeStore, LocalKnowledgeStore

__version__ = "0.1.0"

__all__ = [
    "Chunk",
    "Citation",
    "KnowledgeStore",
    "LightRagStore",
    "LocalKnowledgeStore",
    "RagService",
    "RetrievedChunk",
    "SearchResult",
    "acl",
]
