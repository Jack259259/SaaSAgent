"""知识库存储与检索。默认 LocalKnowledgeStore(本地文件 + 自研混合检索)。

红线 5:ACL 过滤发生在**打分/排序之前**——受限 chunk 不进候选,绝不在生成后兜底。
存储后端可换(postgres / 真 LightRAG)经 KnowledgeStore 接口替换。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from llm import Embedder

from .models import Chunk, RetrievedChunk

VisiblePredicate = Callable[[Chunk], bool]

_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")
_VECTOR_WEIGHT = 0.7
_KEYWORD_WEIGHT = 0.3


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))  # 双方已 L2 归一 → 点积即 cosine


def _freshness_weight(chunk: Chunk) -> float:
    # TODO(阶段后续):按 effective_date 对过期内容降权(§5.3);
    # 避免依赖"当前日期"造成测试不确定,暂为 1.0。
    return 1.0


class KnowledgeStore(Protocol):
    async def insert(self, chunks: list[Chunk]) -> None: ...

    async def search(
        self, query: str, *, visible: VisiblePredicate, top_k: int
    ) -> list[RetrievedChunk]: ...


class LocalKnowledgeStore:
    def __init__(self, *, embedder: Embedder) -> None:
        self._embedder = embedder
        self._chunks: dict[str, Chunk] = {}
        self._file_hashes: dict[str, str] = {}

    async def insert(self, chunks: list[Chunk]) -> None:
        to_embed = [c for c in chunks if not c.embedding]
        if to_embed:
            vectors = await self._embedder.embed([c.text for c in to_embed])
            for chunk, vector in zip(to_embed, vectors, strict=True):
                chunk.embedding = vector
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk

    async def search(
        self, query: str, *, visible: VisiblePredicate, top_k: int
    ) -> list[RetrievedChunk]:
        # 红线 5:先按 ACL 过滤候选,再打分排序;受限 chunk 不进入排序。
        candidates = [c for c in self._chunks.values() if visible(c)]
        if not candidates:
            return []
        (query_vec,) = await self._embedder.embed([query])
        query_tokens = _tokens(query)
        scored: list[RetrievedChunk] = []
        for chunk in candidates:
            vector_score = _cosine(query_vec, chunk.embedding)
            overlap = len(query_tokens & _tokens(chunk.text)) / (len(query_tokens) or 1)
            score = (_VECTOR_WEIGHT * vector_score + _KEYWORD_WEIGHT * overlap) * _freshness_weight(
                chunk
            )
            scored.append(RetrievedChunk(chunk=chunk, score=score))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    # ---- 增量摄取支持 ---------------------------------------------------- #
    def file_hash(self, rel_path: str) -> str | None:
        return self._file_hashes.get(rel_path)

    def set_file_hash(self, rel_path: str, digest: str) -> None:
        self._file_hashes[rel_path] = digest

    def remove_file_hash(self, rel_path: str) -> None:
        self._file_hashes.pop(rel_path, None)

    def remove_doc(self, doc_id: str) -> None:
        for chunk_id in [cid for cid, c in self._chunks.items() if c.doc_id == doc_id]:
            del self._chunks[chunk_id]

    def chunk_count(self) -> int:
        return len(self._chunks)

    # ---- 持久化(本地文件后端)------------------------------------------- #
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "chunks": [c.model_dump() for c in self._chunks.values()],
            "file_hashes": self._file_hashes,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, *, embedder: Embedder) -> LocalKnowledgeStore:
        store = cls(embedder=embedder)
        if not path.is_file():
            return store
        payload = json.loads(path.read_text(encoding="utf-8"))
        for raw in payload.get("chunks", []):
            chunk = Chunk.model_validate(raw)
            store._chunks[chunk.chunk_id] = chunk
        store._file_hashes = dict(payload.get("file_hashes", {}))
        return store
