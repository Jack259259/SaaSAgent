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


# ---- 组合边界补强(W4):多标签并集语义 / 多角色并集 / 租户闸优先 --------------- #
def test_multi_tag_visible_when_any_tag_granted() -> None:
    # 标签维度是"任一命中即可见"(并集语义,见 acl 模块说明):
    # 同时标 internal+public 的片段,对仅有 public 授予的用户仍可见(经 public 命中)。
    tenant = _uc(["tenant_user"])
    assert acl.chunk_visible(tenant, ["internal", "public"]) is True
    assert acl.chunk_visible(tenant, ["internal"]) is False  # 仅 internal 则不可见


def test_multi_role_union_grants_internal() -> None:
    # 多角色取并集:含任一内部角色即获 internal 授予。
    combined = _uc(["tenant_user", "internal_dev"])
    assert acl.granted_tags(combined) == {"public", "tenant", "internal"}


def test_cross_tenant_blocked_even_when_tag_granted() -> None:
    # 内部用户对他租户私有片段:标签可见,但租户闸先拦(红线 9 优先于标签维度)。
    internal_user = _uc(["internal_support"], tenant="t_self")
    assert acl.chunk_allowed(internal_user, tenant_id="t_other", acl_tags=["internal"]) is False
    assert acl.chunk_allowed(internal_user, tenant_id="t_self", acl_tags=["internal"]) is True
