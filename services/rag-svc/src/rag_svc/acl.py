"""检索前 ACL(红线 5 / §9.1 / §9.3)。

两层:KB 级粗 ACL(it_design 仅内部角色,§9.1;无权库根本不查 → §9.3 物理隔离)+
tag 级细 ACL(角色→授予标签集,chunk.acl_tags ∩ 授予 ≠ ∅ 才可见;空标签视为 public)。
真实角色矩阵待业务接入;此处为占位策略,接口稳定。
"""

from __future__ import annotations

from contracts import UserCtx

KB_BUSINESS = "business"
KB_IT_DESIGN = "it_design"

_INTERNAL_ROLES = {"internal", "internal_support", "internal_dev"}
_TENANT_ROLES = {"tenant_user", "tenant_admin"}
_PUBLIC = "public"


def is_internal(user_ctx: UserCtx) -> bool:
    return bool(set(user_ctx.roles) & _INTERNAL_ROLES)


def granted_tags(user_ctx: UserCtx) -> set[str]:
    roles = set(user_ctx.roles)
    if roles & _INTERNAL_ROLES:
        return {"public", "tenant", "internal"}
    if roles & _TENANT_ROLES:
        return {"public", "tenant"}
    return {"public"}


def kb_allowed(user_ctx: UserCtx, kb: str) -> bool:
    """it_design 仅内部角色可查(§9.1);其余库默认可查。"""
    if kb == KB_IT_DESIGN:
        return is_internal(user_ctx)
    return True


def chunk_visible(user_ctx: UserCtx, acl_tags: list[str]) -> bool:
    tags = set(acl_tags) or {_PUBLIC}  # 空标签视为 public
    return bool(tags & granted_tags(user_ctx))
