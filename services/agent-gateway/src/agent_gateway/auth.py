"""鉴权:从 X-User-Ctx 解析 user_ctx(红线 3)。

测试态:客户端在 `X-User-Ctx` 头放 user_ctx 的 JSON。**生产实现见 TODO**:
应由网关验证短时令牌并签发 user_ctx,而非信任客户端头。缺失→401,非法→403,均发 denied 审计。
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from pydantic import ValidationError

from contracts import UserCtx
from contracts.models import ErrorCode, ResultStatus
from orchestrator import anonymous_who, emit_audit, who_from_user_ctx

# 代码仓管理可用角色(内部 / 管理员;租户业务用户无)。与前端 repos.js 同口径。
_REPO_ADMIN_ROLES = {"admin", "repo_admin", "internal", "internal_support", "internal_dev"}


def get_trace_id(x_trace_id: Annotated[str | None, Header()] = None) -> str:
    return x_trace_id or uuid.uuid4().hex


def _deny(status_code: int, detail: str, trace_id: str) -> HTTPException:
    emit_audit(
        who=anonymous_who(),
        tool="chat",
        args_digest="-",
        result_status=ResultStatus.denied,
        trace_id=trace_id,
        error_code=ErrorCode.NO_PERMISSION,
    )
    return HTTPException(status_code=status_code, detail=detail)


def require_user_ctx(
    trace_id: Annotated[str, Depends(get_trace_id)],
    x_user_ctx: Annotated[str | None, Header()] = None,
) -> UserCtx:
    # TODO(生产):改为校验网关签发的短时令牌并由服务端构造 user_ctx,不信任客户端头。
    if not x_user_ctx:
        raise _deny(401, "missing X-User-Ctx (red line 3)", trace_id)
    try:
        data = json.loads(x_user_ctx)
        return UserCtx.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise _deny(403, "invalid user_ctx", trace_id) from exc


def require_repo_admin(
    trace_id: Annotated[str, Depends(get_trace_id)],
    user_ctx: Annotated[UserCtx, Depends(require_user_ctx)],
) -> UserCtx:
    """代码仓管理:功能开关 ``FP_REPO_ADMIN=1`` + 内部管理员角色(红线 3/9;收口 git 子进程攻击面)。

    默认**关闭**(未设开关→404,不暴露端点);开启后非内部管理员→403 + denied 审计。
    """
    if os.environ.get("FP_REPO_ADMIN") != "1":
        raise HTTPException(status_code=404, detail="repo admin disabled")
    if not (set(user_ctx.roles) & _REPO_ADMIN_ROLES):
        emit_audit(
            who=who_from_user_ctx(user_ctx),
            tool="repo_admin",
            args_digest="-",
            result_status=ResultStatus.denied,
            trace_id=trace_id,
            error_code=ErrorCode.NO_PERMISSION,
        )
        raise HTTPException(status_code=403, detail="需要内部管理员角色")
    return user_ctx
