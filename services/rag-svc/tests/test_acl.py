"""ACL 策略:角色→授予标签、KB 粗 ACL、tag 级可见性(红线 5 / §9.1)。"""

from __future__ import annotations

from collections.abc import Sequence

from contracts import UserCtx
from rag_svc import acl


def _uc(roles: Sequence[str]) -> UserCtx:
    return UserCtx(tenant_id="t", user_id="u", roles=list(roles), data_scope={})


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
