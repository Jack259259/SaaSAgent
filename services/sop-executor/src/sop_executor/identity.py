"""执行身份:发起用户短时令牌代持(桩)。

红线 4 / §5.4:执行身份 = 发起用户,权限即用户权限,杜绝服务账号越权。
**桩实现**:返回占位令牌串;生产应由网关签发短时令牌、执行器据 user_ctx 换取并随 api 调用透传。
"""

from __future__ import annotations

from contracts import UserCtx


def mint_user_token(user_ctx: UserCtx) -> str:
    return f"stub-token:{user_ctx.tenant_id}:{user_ctx.user_id}"
