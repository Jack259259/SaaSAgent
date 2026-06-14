"""MemoryService:分层记忆存取门面(方案 §7)。

全程按 (tenant_id, user_id) 限定(红线 9);写入过脱敏 + 重要性门槛;存脱敏后内容。
经验仅 reflection-worker 可录(record_experience 角色闸);本阶段不建反思管道。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from contracts import UserCtx
from llm import Embedder, HashingEmbedder

from .importance import normalize, should_store
from .models import (
    ExperienceEntry,
    MemoryHit,
    MemoryKind,
    OpeningContext,
    SaveResult,
    StoredMemory,
)
from .redaction import BasicRedactor, Redactor
from .store import InMemoryMemoryStore, MemoryStore

_REFLECTION_ROLE = "reflection_worker"
_EXPERIENCE_IMPORTANCE = 0.7


class MemoryService:
    def __init__(
        self,
        *,
        store: MemoryStore | None = None,
        embedder: Embedder | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        self._store = store or InMemoryMemoryStore()
        self._embedder = embedder or HashingEmbedder()
        self._redactor = redactor or BasicRedactor()

    # ---- 写入 ------------------------------------------------------------ #
    async def save_profile(
        self, user_ctx: UserCtx, content: str, *, scope: str = "profile", importance: float = 0.5
    ) -> SaveResult:
        return await self._save(
            user_ctx, MemoryKind.profile, content, scope=scope, importance=importance
        )

    async def save_episodic(
        self, user_ctx: UserCtx, summary: str, *, importance: float = 0.5
    ) -> SaveResult:
        return await self._save(user_ctx, MemoryKind.episodic, summary, importance=importance)

    async def record_experience(self, user_ctx: UserCtx, entry: ExperienceEntry) -> SaveResult:
        # 红线:经验库仅 reflection-worker 可写(本阶段无反思管道,仅留接口 + 角色闸)。
        if _REFLECTION_ROLE not in user_ctx.roles:
            raise PermissionError("经验库仅 reflection-worker 可写")
        content = (
            f"任务:{entry.task_signature}\n适用:{entry.applicability}\n"
            f"有效路径:{entry.effective_path}\n坑:{entry.pitfalls}\n成本:{entry.cost}"
        )
        search_text = f"{entry.task_signature} {entry.applicability} {' '.join(entry.tags)}"
        mem = await self._make(
            user_ctx,
            MemoryKind.experience,
            content=self._redactor.redact(content),
            search_text=self._redactor.redact(search_text),
            importance=_EXPERIENCE_IMPORTANCE,
            tags=entry.tags,
        )
        self._store.add(mem)
        return SaveResult(memory_id=mem.memory_id, stored=True)

    async def _save(
        self,
        user_ctx: UserCtx,
        kind: MemoryKind,
        content: str,
        *,
        scope: str = "",
        importance: float = 0.5,
    ) -> SaveResult:
        clean = self._redactor.redact(content)
        existing = {
            normalize(m.content)
            for m in self._store.list_kind(user_ctx.tenant_id, user_ctx.user_id, kind)
        }
        if not should_store(importance, clean, existing):
            return SaveResult(memory_id="", stored=False)
        mem = await self._make(
            user_ctx, kind, content=clean, search_text=clean, scope=scope, importance=importance
        )
        self._store.add(mem)
        return SaveResult(memory_id=mem.memory_id, stored=True)

    async def _make(
        self,
        user_ctx: UserCtx,
        kind: MemoryKind,
        *,
        content: str,
        search_text: str,
        scope: str = "",
        importance: float = 0.5,
        tags: list[str] | None = None,
    ) -> StoredMemory:
        (embedding,) = await self._embedder.embed([search_text])
        return StoredMemory(
            memory_id=uuid.uuid4().hex,
            tenant_id=user_ctx.tenant_id,
            user_id=user_ctx.user_id,
            kind=kind,
            content=content,
            search_text=search_text,
            scope=scope,
            importance=importance,
            tags=tags or [],
            embedding=embedding,
            created_at=datetime.now(UTC).isoformat(),
        )

    # ---- 读取 ------------------------------------------------------------ #
    async def search_memory(
        self,
        user_ctx: UserCtx,
        query: str,
        *,
        kinds: list[MemoryKind] | None = None,
        top_k: int = 5,
    ) -> list[MemoryHit]:
        target = set(kinds or [MemoryKind.episodic, MemoryKind.experience])
        (query_embedding,) = await self._embedder.embed([query])
        scored = self._store.search(
            user_ctx.tenant_id, user_ctx.user_id, target, query_embedding, top_k
        )
        return [MemoryHit(kind=m.kind, content=m.content, score=score) for m, score in scored]

    async def opening_context(
        self, user_ctx: UserCtx, *, query: str = "", memory_k: int = 3, experience_k: int = 3
    ) -> OpeningContext:
        profile = [
            m.content
            for m in self._store.list_kind(user_ctx.tenant_id, user_ctx.user_id, MemoryKind.profile)
        ]
        (query_embedding,) = await self._embedder.embed([query or "近期相关"])
        memories = [
            MemoryHit(kind=m.kind, content=m.content, score=s)
            for m, s in self._store.search(
                user_ctx.tenant_id,
                user_ctx.user_id,
                {MemoryKind.episodic},
                query_embedding,
                memory_k,
            )
        ]
        experiences = [
            MemoryHit(kind=m.kind, content=m.content, score=s)
            for m, s in self._store.search(
                user_ctx.tenant_id,
                user_ctx.user_id,
                {MemoryKind.experience},
                query_embedding,
                experience_k,
            )
        ]
        return OpeningContext(profile=profile, memories=memories, experiences=experiences)
