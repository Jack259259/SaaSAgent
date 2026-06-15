"""红线 9:跨租户绝不互见(rag 检索 / memory 记忆 / 会话工作区);经验写入受角色闸(红线 4)。"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from contracts import UserCtx
from memory_svc import ExperienceEntry, MemoryService
from orchestrator import SessionAccessError, SessionStore
from rag_svc import RagService, acl
from rag_svc.ingest import ingest_dir


def _uc(tenant: str, *, user: str = "u", roles: Sequence[str] | None = None) -> UserCtx:
    return UserCtx(
        tenant_id=tenant, user_id=user, roles=list(roles or ["tenant_user"]), data_scope={}
    )


async def test_rag_cross_tenant_private_not_visible(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "p.md").write_text(
        "---\nsource: 客户ACME/专属口径\nacl_tags: [tenant]\n---\nACME 专属执行率口径。\n",
        encoding="utf-8",
    )
    store = tmp_path / "store"
    await ingest_dir(kb=acl.KB_BUSINESS, src=src, store_dir=store, tenant="t_acme")
    svc = RagService.from_dir(store)

    owner = await svc.search_knowledge(_uc("t_acme"), "口径", kb=acl.KB_BUSINESS, top_k=10)
    assert owner.chunks  # 本租户可见(对照)
    other = await svc.search_knowledge(_uc("t_other"), "口径", kb=acl.KB_BUSINESS, top_k=10)
    assert other.chunks == [] and other.citations == []  # 跨租户零证据(红线 9)


async def test_memory_cross_tenant_not_visible() -> None:
    svc = MemoryService()
    await svc.save_episodic(_uc("t1"), "偏好:优先看华东执行率", importance=0.9)
    assert await svc.search_memory(_uc("t1"), "华东执行率")  # 本租户可检索(对照)
    assert await svc.search_memory(_uc("t2"), "华东执行率") == []  # 跨租户不可见


async def test_experience_write_requires_reflection_role() -> None:
    svc = MemoryService()
    entry = ExperienceEntry(
        task_signature="取数-执行率", applicability="月报", effective_path="query→summarize"
    )
    with pytest.raises(PermissionError):
        await svc.record_experience(
            _uc("t1", roles=["analyst"]), entry
        )  # 非 reflection-worker 拒绝


def test_session_cross_tenant_denied() -> None:
    store = SessionStore()
    sess = store.create(user_ctx=_uc("t1"), trace_id="t")
    with pytest.raises(SessionAccessError):
        store.get(sess.session_id, _uc("t2"))  # 工作区随会话,跨租户取会话被拒
