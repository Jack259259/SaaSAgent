"""ACL 策略:角色→授予标签、KB 粗 ACL、tag 级可见性(红线 5 / §9.1)。"""

from __future__ import annotations

from collections.abc import Sequence

from contracts import UserCtx
from rag_svc import acl


def _uc(roles: Sequence[str], tenant: str = "t") -> UserCtx:
    return UserCtx(tenant_id=tenant, user_id="u", roles=list(roles), data_scope={})


def test_granted_tags_by_role() -> None:
    assert acl.granted_tags(_uc(["internal_support"])) == {"public", "tenant", "internal"}
    assert acl.granted_tags(_uc(["tenant_user"])) == {"public", "tenant"}
    assert acl.granted_tags(_uc([])) == {"public"}


def test_it_design_internal_only() -> None:
    assert acl.kb_allowed(_uc(["internal_dev"]), acl.KB_IT_DESIGN) is True
    assert acl.kb_allowed(_uc(["tenant_user"]), acl.KB_IT_DESIGN) is False
    assert acl.kb_allowed(_uc(["tenant_user"]), acl.KB_BUSINESS) is True


def test_chunk_visible() -> None:
    tenant = _uc(["tenant_user"])
    assert acl.chunk_visible(tenant, ["public"]) is True
    assert acl.chunk_visible(tenant, ["tenant"]) is True
    assert acl.chunk_visible(tenant, ["internal"]) is False
    assert acl.chunk_visible(_uc(["internal_support"]), ["internal"]) is True
    assert acl.chunk_visible(tenant, []) is True  # 空标签视为 public


def test_tenant_allowed() -> None:
    acme = _uc(["tenant_user"], tenant="t_acme")
    assert acl.tenant_allowed(acme, None) is True  # 全局对所有租户可见
    assert acl.tenant_allowed(acme, "t_acme") is True  # 本租户私有可见
    assert acl.tenant_allowed(acme, "t_other") is False  # 他租户私有不可见(红线 9)


def test_chunk_allowed_tenant_and_tag() -> None:
    acme = _uc(["tenant_user"], tenant="t_acme")
    # 标签可见但属他租户 → 不进候选(红线 9 与标签同为前置过滤)
    assert acl.chunk_allowed(acme, tenant_id="t_other", acl_tags=["tenant"]) is False
    assert acl.chunk_allowed(acme, tenant_id="t_acme", acl_tags=["tenant"]) is True  # 本租户
    assert acl.chunk_allowed(acme, tenant_id=None, acl_tags=["public"]) is True  # 全局
    # 本租户但标签不可见(internal)→ 标签维度仍生效
    assert acl.chunk_allowed(acme, tenant_id="t_acme", acl_tags=["internal"]) is False
