"""零信任权限校验(红线 3)。工具侧二次校验,不信任编排器上游。"""

from __future__ import annotations

from typing import Protocol

from contracts import ToolSpec, UserCtx
from contracts.models import ErrorCode


class NoPermissionError(Exception):
    """越权 / 缺 user_ctx;映射到 ToolSpec 错误 NO_PERMISSION。"""

    code = ErrorCode.NO_PERMISSION


def assert_user_ctx(user_ctx: UserCtx | None) -> UserCtx:
    """user_ctx 缺失即拒(红线 3)。"""
    if user_ctx is None:
        raise NoPermissionError("缺少 user_ctx(红线 3)")
    return user_ctx


class PermissionChecker(Protocol):
    def check(self, user_ctx: UserCtx, spec: ToolSpec) -> None: ...


class DefaultPermissionChecker:
    """占位 RBAC 策略(接口化,真实矩阵见 §9.1):

    user_ctx.permissions 含 "*" 通配,或显式含该工具的 permission_scope 即放行;否则拒绝。
    """

    def check(self, user_ctx: UserCtx, spec: ToolSpec) -> None:
        perms = set(user_ctx.permissions)
        if "*" in perms or spec.permission_scope in perms:
            return
        raise NoPermissionError(f"无权限:{spec.permission_scope}")
