"""知识图谱查询(MockProvider + fixture):截断/度排序、中心子图、节点详情、搜索;ACL 预过滤负例。"""

from __future__ import annotations

from collections.abc import Sequence

from contracts import UserCtx
from rag_svc import MockGraphProvider, RagService, acl


def _svc() -> RagService:
    return RagService(stores={}, graph_provider=MockGraphProvider())


def _uc(roles: Sequence[str], tenant: str = "t_acme") -> UserCtx:
    return UserCtx(tenant_id=tenant, user_id="u", roles=list(roles), data_scope={})


def _internal(tenant: str = "t_acme") -> UserCtx:
    return _uc(["internal_dev"], tenant)


# ── get_graph:截断 + 度排序 + 中心子图 + 类型过滤 ───────────────────────────────── #
async def test_get_graph_max_nodes_truncate_and_degree_order() -> None:
    svc = _svc()
    data = await svc.get_graph(_internal(), acl.KB_BUSINESS, max_nodes=3)
    assert len(data.nodes) == 3
    assert data.is_truncated is True  # business 全集 > 3
    assert data.nodes[0].entity_id == "资金计划"  # 度最高的 hub 居首
    assert data.nodes[0].degree is not None and data.nodes[0].degree >= 5
    assert data.stats.total_nodes == 3 and data.stats.total_edges == len(data.edges)


async def test_get_graph_full_for_internal() -> None:
    # 内部用户拿到 business 全部公开+内部+本租户(t_acme)节点,但拿不到他租户(t_other)节点。
    data = await _svc().get_graph(_internal(tenant="t_acme"), acl.KB_BUSINESS, max_nodes=200)
    ids = {n.entity_id for n in data.nodes}
    assert "内部审计口径" in ids  # internal 标签可见
    assert "ACME专属调度" in ids  # 本租户私有可见
    assert "他司预算" not in ids  # 跨租户不可见(红线 9)
    assert data.is_truncated is False


async def test_get_graph_center_entity_subgraph() -> None:
    data = await _svc().get_graph(
        _internal(), acl.KB_BUSINESS, center_entity="执行率", max_nodes=200
    )
    ids = {n.entity_id for n in data.nodes}
    assert "执行率" in ids and "资金计划" in ids  # 中心 + 1跳
    assert "授信额度" in ids  # 2 跳(资金计划→授信额度)可达


async def test_get_graph_entity_type_filter() -> None:
    data = await _svc().get_graph(
        _internal(), acl.KB_BUSINESS, entity_types=["指标"], max_nodes=200
    )
    assert {n.entity_type for n in data.nodes} == {"指标"}
    assert any(n.entity_id == "执行率" for n in data.nodes)


# ── get_node:depth 邻居 ─────────────────────────────────────────────────────────── #
async def test_get_node_depth_neighbors() -> None:
    detail = await _svc().get_node(_internal(), acl.KB_BUSINESS, "资金计划", depth=1)
    assert detail.node is not None and detail.node.entity_id == "资金计划"
    neighbor_ids = {n.entity_id for n in detail.neighbors}
    assert "执行率" in neighbor_ids and "现金流量表" in neighbor_ids


async def test_get_node_missing_returns_none() -> None:
    detail = await _svc().get_node(_internal(), acl.KB_BUSINESS, "不存在的实体", depth=1)
    assert detail.node is None and detail.neighbors == []


# ── search_graph_nodes:模糊匹配 ──────────────────────────────────────────────────── #
async def test_search_nodes_fuzzy() -> None:
    res = await _svc().search_graph_nodes(_internal(), acl.KB_BUSINESS, "执行", top_k=10)
    assert any(n.entity_id == "执行率" for n in res.entities)


async def test_search_nodes_description_mode() -> None:
    res = await _svc().search_graph_nodes(
        _internal(), acl.KB_BUSINESS, "融资", top_k=10, search_in="description"
    )
    assert any(n.entity_id == "授信额度" for n in res.entities)  # 描述含"融资"


# ── ACL 预过滤负例(红线 5/9):无权 user_ctx 拿不到受限节点/边 ──────────────────── #
async def test_acl_non_internal_cannot_see_internal_node() -> None:
    # tenant_user 非内部 → 看不到 acl_tags=[internal] 的"内部审计口径"及其边。
    data = await _svc().get_graph(_uc(["tenant_user"], "t_acme"), acl.KB_BUSINESS, max_nodes=200)
    ids = {n.entity_id for n in data.nodes}
    assert "内部审计口径" not in ids
    assert all("内部审计口径" not in (e.source_id, e.target_id) for e in data.edges)
    assert "资金计划" in ids  # 公开节点仍在


async def test_acl_cross_tenant_isolation() -> None:
    # t_other 的 tenant_user:看不到 t_acme 私有节点;t_acme 的看不到 t_other 私有节点(红线 9)。
    acme = await _svc().get_graph(_uc(["tenant_user"], "t_acme"), acl.KB_BUSINESS, max_nodes=200)
    other = await _svc().get_graph(_uc(["tenant_user"], "t_other"), acl.KB_BUSINESS, max_nodes=200)
    acme_ids = {n.entity_id for n in acme.nodes}
    other_ids = {n.entity_id for n in other.nodes}
    assert "ACME专属调度" in acme_ids and "他司预算" not in acme_ids
    assert "他司预算" in other_ids and "ACME专属调度" not in other_ids


async def test_acl_get_node_restricted_center_hidden() -> None:
    # 非内部直接点名受限中心节点 → node=None(不经详情泄露)。
    detail = await _svc().get_node(
        _uc(["tenant_user"], "t_acme"), acl.KB_BUSINESS, "内部审计口径", depth=1
    )
    assert detail.node is None


async def test_acl_it_design_kb_internal_only() -> None:
    # it_design 库:非内部角色根本查不到(kb_allowed 拦截,§9.1/§9.3)。
    denied = await _svc().get_graph(_uc(["tenant_user"]), acl.KB_IT_DESIGN, max_nodes=200)
    assert denied.nodes == [] and denied.stats.total_nodes == 0
    allowed = await _svc().get_graph(_internal(), acl.KB_IT_DESIGN, max_nodes=200)
    assert len(allowed.nodes) > 0


async def test_no_provider_returns_empty() -> None:
    # 未注入 graph_provider(如纯检索部署)→ 空图,不报错。
    svc = RagService(stores={})
    data = await svc.get_graph(_internal(), acl.KB_BUSINESS)
    assert data.nodes == [] and data.stats.total_nodes == 0
