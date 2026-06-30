"""RagService 双库 + 检索前 ACL + 引用;ingest 空目录幂等 + hash 增量。"""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from pathlib import Path

import pytest

from contracts import UserCtx
from llm import MockProvider, NotConfiguredError
from rag_svc import RagService, acl, graph_working_dir
from rag_svc.ingest import ingest_dir

_FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"


def _uc(roles: Sequence[str], tenant: str = "t") -> UserCtx:
    return UserCtx(tenant_id=tenant, user_id="u", roles=list(roles), data_scope={})


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


async def test_tenant_private_not_cross_visible(tmp_path: Path) -> None:
    # 一篇"租户私有"业务文档(acl_tags=tenant),以 t_acme 摄取;t_other 绝不可见(红线 9)。
    src = tmp_path / "acme_docs"
    src.mkdir()
    (src / "private.md").write_text(
        "---\n"
        "source: 客户ACME/专属口径\n"
        "acl_tags: [tenant]\n"
        "---\n"
        "资金计划执行率的 ACME 专属口径说明。\n",
        encoding="utf-8",
    )
    store_dir = tmp_path / "store"
    await ingest_dir(kb=acl.KB_BUSINESS, src=src, store_dir=store_dir, tenant="t_acme")
    svc = RagService.from_dir(store_dir)

    acme = await svc.search_knowledge(
        _uc(["tenant_user"], tenant="t_acme"), "执行率口径", kb=acl.KB_BUSINESS, top_k=10
    )
    assert any("ACME" in c.source for c in acme.citations)  # 本租户可见

    other = await svc.search_knowledge(
        _uc(["tenant_user"], tenant="t_other"), "执行率口径", kb=acl.KB_BUSINESS, top_k=10
    )
    assert other.chunks == []  # 跨租户绝不互见(红线 9)
    assert other.summary == "未在知识库中找到依据。"


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


async def test_graph_params_default_is_noop(tmp_path: Path) -> None:
    # 加法式回归锁:graph_dir/graph_provider 缺省 == 显式 None,均不建图、stats 不变(默认/CI 路径)。
    default = await ingest_dir(kb=acl.KB_BUSINESS, src=_FIXTURES, store_dir=tmp_path / "s1")
    explicit = await ingest_dir(
        kb=acl.KB_BUSINESS,
        src=_FIXTURES,
        store_dir=tmp_path / "s2",
        graph_dir=None,
        graph_provider=None,
    )
    assert default == explicit
    assert not (tmp_path / "s2" / ".graph").exists()  # 未传 graph_dir → 不碰图


async def test_rebuild_graph_guards_against_wipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # lightrag 不可用时 _rebuild_graph 必须先报错、不 rmtree 掉已有图(防误配入库清空图)。
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: None if name == "lightrag" else real(name, *a, **k),
    )
    wd = tmp_path / "g" / acl.KB_BUSINESS / "_global"
    wd.mkdir(parents=True)
    keep = wd / "graph_chunk_entity_relation.graphml"
    keep.write_text("KEEP", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "d.md").write_text("# 标题\n资金计划是对未来资金收支的预测与安排。", encoding="utf-8")

    with pytest.raises(NotConfiguredError):
        await ingest_dir(
            kb=acl.KB_BUSINESS,
            src=src,
            store_dir=tmp_path / "i",
            graph_dir=tmp_path / "g",
            graph_provider=MockProvider([]),
        )
    assert keep.read_text(encoding="utf-8") == "KEEP"  # 已有图未被清空


class _FakeGraphStore:
    """假 LightRagStore:把 graphml 写进各自 working_dir(避开真实 LLM/库),供重建/替换测试。"""

    written = "NEW"

    def __init__(self, *, working_dir: Path, embedder: object, provider: object) -> None:
        self._wd = working_dir

    async def insert(self, chunks: object) -> None:
        (self._wd / "graph_chunk_entity_relation.graphml").write_text(
            self.written, encoding="utf-8"
        )

    async def finalize(self) -> None:
        pass


def _fake_lightrag_available(monkeypatch: pytest.MonkeyPatch) -> None:
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: object() if name == "lightrag" else real(name, *a, **k),
    )


def _seed_graph_and_src(tmp_path: Path) -> tuple[Path, Path, Path]:
    g = tmp_path / "g"
    wd = graph_working_dir(g, acl.KB_BUSINESS, None)
    wd.mkdir(parents=True)
    (wd / "graph_chunk_entity_relation.graphml").write_text("OLD", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "d.md").write_text("# 标题\n资金计划是对未来资金收支的预测与安排。", encoding="utf-8")
    return g, wd, src


async def test_rebuild_graph_atomic_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 「重新入库」把新图原子换入、旧图被替换,且无 .tmp-/.old- 残留。
    _fake_lightrag_available(monkeypatch)
    monkeypatch.setattr("rag_svc.ingest.LightRagStore", _FakeGraphStore)
    g, wd, src = _seed_graph_and_src(tmp_path)

    await ingest_dir(
        kb=acl.KB_BUSINESS,
        src=src,
        store_dir=tmp_path / "i",
        graph_dir=g,
        graph_provider=MockProvider([]),
    )

    assert (wd / "graph_chunk_entity_relation.graphml").read_text(encoding="utf-8") == "NEW"
    assert [p.name for p in wd.parent.iterdir()] == ["_global"]  # 无临时/备份残留


async def test_rebuild_graph_keeps_old_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 重建中途失败(LLM 抽取抛错)→ 旧图原样保留、临时清理、异常上抛(调用方将置 job=failed)。
    _fake_lightrag_available(monkeypatch)

    class _BoomStore(_FakeGraphStore):
        async def insert(self, chunks: object) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr("rag_svc.ingest.LightRagStore", _BoomStore)
    g, wd, src = _seed_graph_and_src(tmp_path)

    with pytest.raises(RuntimeError):
        await ingest_dir(
            kb=acl.KB_BUSINESS,
            src=src,
            store_dir=tmp_path / "i",
            graph_dir=g,
            graph_provider=MockProvider([]),
        )

    assert (wd / "graph_chunk_entity_relation.graphml").read_text(encoding="utf-8") == "OLD"
    assert [p.name for p in wd.parent.iterdir()] == ["_global"]  # 临时已清,仅旧图在
