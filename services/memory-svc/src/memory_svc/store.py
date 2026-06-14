"""记忆存储。InMemoryMemoryStore(postgres TODO);**分区键 = (tenant_id, user_id)**。

跨租户/跨用户天然不可见(不同分区键),红线 9 在存储层即成立。向量检索对预存 embedding 做 cosine。
"""

from __future__ import annotations

from typing import Protocol

from .models import MemoryKind, StoredMemory


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))  # 双方已 L2 归一 → 点积即 cosine


class MemoryStore(Protocol):
    def add(self, mem: StoredMemory) -> None: ...

    def list_kind(self, tenant_id: str, user_id: str, kind: MemoryKind) -> list[StoredMemory]: ...

    def search(
        self,
        tenant_id: str,
        user_id: str,
        kinds: set[MemoryKind],
        query_embedding: list[float],
        top_k: int,
    ) -> list[tuple[StoredMemory, float]]: ...


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], list[StoredMemory]] = {}

    def add(self, mem: StoredMemory) -> None:
        self._items.setdefault((mem.tenant_id, mem.user_id), []).append(mem)

    def list_kind(self, tenant_id: str, user_id: str, kind: MemoryKind) -> list[StoredMemory]:
        return [m for m in self._items.get((tenant_id, user_id), []) if m.kind == kind]

    def search(
        self,
        tenant_id: str,
        user_id: str,
        kinds: set[MemoryKind],
        query_embedding: list[float],
        top_k: int,
    ) -> list[tuple[StoredMemory, float]]:
        items = [m for m in self._items.get((tenant_id, user_id), []) if m.kind in kinds]
        scored = [(m, _cosine(query_embedding, m.embedding)) for m in items]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
