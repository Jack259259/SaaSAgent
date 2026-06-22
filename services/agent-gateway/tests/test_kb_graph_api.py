"""知识图谱端点(/admin/kb/graph*):角色门控 + IT 库细 ACL + 跨租户隔离 + 入参越界 + 开关隐藏。

默认引擎 = MockGraphProvider(fixture 带 tenant/acl);安全负例为重点(红线 3/5/9)。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent_gateway import deps
from agent_gateway.app import app


def _ctx(roles: list[str], tenant: str = "t_acme") -> str:
    return json.dumps(
        {"tenant_id": tenant, "user_id": "u", "roles": roles, "data_scope": {}, "permissions": []}
    )


_INTERNAL = _ctx(["internal_dev"])  # 内部管理员(可访问 it_design)
_KB_ADMIN = _ctx(["kb_admin"])  # 管理员但非内部(business 可,it_design 不可)
_USER = _ctx(["tenant_user"])  # 非管理员


@pytest.fixture(autouse=True)
def _reset_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    # 默认引擎 mock;清掉单例缓存,避免跨用例串引擎。
    monkeypatch.delenv("FP_KB_GRAPH", raising=False)
    monkeypatch.delenv("FP_KB_GRAPH_ENGINE", raising=False)
    deps._KB_GRAPH_PROVIDER = None


# ── 角色门控(红线 3)───────────────────────────────────────────────────────────── #
def test_missing_ctx_401() -> None:
    r = TestClient(app).get("/admin/kb/graph", params={"kb": "business"})
    assert r.status_code == 401


def test_non_admin_403() -> None:
    r = TestClient(app).get(
        "/admin/kb/graph", params={"kb": "business"}, headers={"X-User-Ctx": _USER}
    )
    assert r.status_code == 403


def test_admin_graph_happy() -> None:
    r = TestClient(app).get(
        "/admin/kb/graph",
        params={"kb": "business", "max_nodes": 3},
        headers={"X-User-Ctx": _INTERNAL},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kb"] == "business" and len(body["nodes"]) == 3 and body["is_truncated"] is True
    assert body["stats"]["total_nodes"] == 3


# ── IT 库细 ACL(红线 5/§9.1)──────────────────────────────────────────────────── #
def test_it_design_non_internal_403() -> None:
    r = TestClient(app).get(
        "/admin/kb/graph", params={"kb": "it_design"}, headers={"X-User-Ctx": _KB_ADMIN}
    )
    assert r.status_code == 403


def test_it_design_internal_ok() -> None:
    r = TestClient(app).get(
        "/admin/kb/graph", params={"kb": "it_design"}, headers={"X-User-Ctx": _INTERNAL}
    )
    assert r.status_code == 200 and len(r.json()["nodes"]) > 0


# ── 非法 kb(防注入:枚举)───────────────────────────────────────────────────────── #
def test_invalid_kb_404() -> None:
    r = TestClient(app).get(
        "/admin/kb/graph", params={"kb": "evil"}, headers={"X-User-Ctx": _INTERNAL}
    )
    assert r.status_code == 404


# ── 功能开关:FP_KB_GRAPH=0 → 端点完全隐藏(404)──────────────────────────────── #
def test_disabled_flag_hides_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_KB_GRAPH", "0")
    c = TestClient(app)
    assert (
        c.get(
            "/admin/kb/graph", params={"kb": "business"}, headers={"X-User-Ctx": _INTERNAL}
        ).status_code
        == 404
    )
    assert (
        c.get(
            "/admin/kb/graph/node/资金计划",
            params={"kb": "business"},
            headers={"X-User-Ctx": _INTERNAL},
        ).status_code
        == 404
    )
    assert (
        c.get(
            "/admin/kb/graph/search",
            params={"kb": "business", "q": "资金"},
            headers={"X-User-Ctx": _INTERNAL},
        ).status_code
        == 404
    )


# ── 跨租户隔离(红线 9):返回不含他租户实体 ──────────────────────────────────── #
def test_cross_tenant_excludes_other_tenant_entities() -> None:
    # 管理员需为可访问端点的角色;internal_dev 有 tenant 标签授予,但租户维度仍按 tenant_id 隔离。
    c = TestClient(app)
    acme = c.get(
        "/admin/kb/graph",
        params={"kb": "business", "max_nodes": 200},
        headers={"X-User-Ctx": _ctx(["internal_dev"], "t_acme")},
    ).json()
    acme_ids = {n["entity_id"] for n in acme["nodes"]}
    assert "ACME专属调度" in acme_ids  # 本租户私有可见
    assert "他司预算" not in acme_ids  # 他租户私有不可见(红线 9)
    # 反向:t_other 的内部管理员看不到 t_acme 私有,但看得到自己租户的"他司预算"。
    other = c.get(
        "/admin/kb/graph",
        params={"kb": "business", "max_nodes": 200},
        headers={"X-User-Ctx": _ctx(["internal_dev"], "t_other")},
    ).json()
    other_ids = {n["entity_id"] for n in other["nodes"]}
    assert "他司预算" in other_ids and "ACME专属调度" not in other_ids


# ── 入参越界 → 422 ──────────────────────────────────────────────────────────────── #
def test_max_nodes_out_of_range_422() -> None:
    c = TestClient(app)
    assert (
        c.get(
            "/admin/kb/graph",
            params={"kb": "business", "max_nodes": 0},
            headers={"X-User-Ctx": _INTERNAL},
        ).status_code
        == 422
    )
    assert (
        c.get(
            "/admin/kb/graph",
            params={"kb": "business", "max_nodes": 9999},
            headers={"X-User-Ctx": _INTERNAL},
        ).status_code
        == 422
    )


def test_depth_out_of_range_422() -> None:
    r = TestClient(app).get(
        "/admin/kb/graph/node/资金计划",
        params={"kb": "business", "depth": 9},
        headers={"X-User-Ctx": _INTERNAL},
    )
    assert r.status_code == 422


def test_top_k_out_of_range_422() -> None:
    r = TestClient(app).get(
        "/admin/kb/graph/search",
        params={"kb": "business", "q": "资金", "top_k": 999},
        headers={"X-User-Ctx": _INTERNAL},
    )
    assert r.status_code == 422


def test_search_in_invalid_422() -> None:
    r = TestClient(app).get(
        "/admin/kb/graph/search",
        params={"kb": "business", "q": "资金", "search_in": "bogus"},
        headers={"X-User-Ctx": _INTERNAL},
    )
    assert r.status_code == 422


# ── node / search happy ─────────────────────────────────────────────────────────── #
def test_node_detail_happy() -> None:
    r = TestClient(app).get(
        "/admin/kb/graph/node/资金计划",
        params={"kb": "business", "depth": 1},
        headers={"X-User-Ctx": _INTERNAL},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["node"]["entity_id"] == "资金计划" and len(body["neighbors"]) > 0


def test_search_happy() -> None:
    r = TestClient(app).get(
        "/admin/kb/graph/search",
        params={"kb": "business", "q": "执行", "top_k": 5},
        headers={"X-User-Ctx": _INTERNAL},
    )
    assert r.status_code == 200
    assert any(n["entity_id"] == "执行率" for n in r.json()["entities"])
