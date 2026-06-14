"""RagService 双库 + 检索前 ACL + 引用;ingest 空目录幂等 + hash 增量。"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from contracts import UserCtx
from rag_svc import RagService, acl
from rag_svc.ingest import ingest_dir

_FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"


def _uc(roles: Sequence[str]) -> UserCtx:
    return UserCtx(tenant_id="t", user_id="u", roles=list(roles), data_scope={})


async def test_business_acl_prefilter(tmp_path: Path) -> None:
    await ingest_dir(kb=acl.KB_BUSINESS, src=_FIXTURES, store_dir=tmp_path)
    svc = RagService.from_dir(tmp_path)

    tenant = await svc.search_knowledge(
        _uc(["tenant_user"]), "执行率口径", kb=acl.KB_BUSINESS, top_k=10
    )
    tenant_sources = [c.source for c in tenant.citations]
    assert any("公开" in s for s in tenant_sources)  # public 可见
    assert not any("内部" in s for s in tenant_sources)  # internal 不可见(红线 5)

    internal = await svc.search_knowledge(
        _uc(["internal_support"]), "执行率口径", kb=acl.KB_BUSINESS, top_k=10
    )
    assert any("内部" in c.source for c in internal.citations)  # 内部用户可见内部片段


async def test_it_design_kb_internal_only(tmp_path: Path) -> None:
    await ingest_dir(kb=acl.KB_IT_DESIGN, src=_FIXTURES, store_dir=tmp_path)
    svc = RagService.from_dir(tmp_path)

    tenant = await svc.search_knowledge(_uc(["tenant_user"]), "执行率", kb=acl.KB_IT_DESIGN)
    assert tenant.chunks == []  # §9.1/§9.3:无权库根本不查
    assert tenant.summary == "未在知识库中找到依据。"

    internal = await svc.search_knowledge(_uc(["internal_dev"]), "执行率", kb=acl.KB_IT_DESIGN)
    assert len(internal.chunks) > 0


async def test_citations_complete(tmp_path: Path) -> None:
    await ingest_dir(kb=acl.KB_BUSINESS, src=_FIXTURES, store_dir=tmp_path)
    svc = RagService.from_dir(tmp_path)
    result = await svc.search_knowledge(
        _uc(["internal_support"]), "执行率", kb=acl.KB_BUSINESS, top_k=3
    )
    assert result.citations
    for citation in result.citations:
        assert citation.source
        assert citation.location


async def test_empty_dir_ingest_idempotent(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    store_dir = tmp_path / "store"
    first = await ingest_dir(kb=acl.KB_BUSINESS, src=empty, store_dir=store_dir)
    assert first["files"] == 0
    assert first["docs"] == 0
    second = await ingest_dir(kb=acl.KB_BUSINESS, src=empty, store_dir=store_dir)
    assert second == first  # 幂等空跑


async def test_incremental_hash_skip(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    first = await ingest_dir(kb=acl.KB_BUSINESS, src=_FIXTURES, store_dir=store_dir)
    assert first["docs"] == 3
    assert first["skipped"] == 0
    second = await ingest_dir(kb=acl.KB_BUSINESS, src=_FIXTURES, store_dir=store_dir)
    assert second["docs"] == 0
    assert second["skipped"] == 3  # 未变更全跳过
