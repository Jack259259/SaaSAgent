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
