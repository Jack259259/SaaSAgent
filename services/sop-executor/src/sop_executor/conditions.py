"""preconditions 核验 与 postconditions 回查(方案 §5.4)。

preconditions:权限核验(结构化,强制);prerequisite_state / blocking_when 为描述性(记入报告)。
  注:可执行的"业务前置 API 核验"需 schema 增槽位(当前 schema 的 preconditions 无 api 字段)——TODO。
postconditions:按 verify.api 发起回查 + verify.expect 逐项比对;**失败即整体失败,绝不报成功**(红线)。
"""

from __future__ import annotations

from typing import Any

from contracts import UserCtx

from .httpcaller import HttpCaller
from .models import Sop, StepResult
from .templating import resolve


def check_preconditions(sop: Sop, user_ctx: UserCtx) -> StepResult:
    perms = set(user_ctx.permissions)
    if "*" not in perms:
        missing = [p for p in sop.preconditions.permissions if p not in perms]
        if missing:
            return StepResult(
                kind="precondition", name="permissions", ok=False, detail=f"缺少权限:{missing}"
            )
    return StepResult(kind="precondition", name="permissions", ok=True, detail="权限校验通过")


def dig(data: Any, dotted: str) -> Any:
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


async def check_postconditions(
    sop: Sop, http: HttpCaller, token: str, context: dict[str, Any]
) -> StepResult:
    verify = sop.postconditions.verify
    if verify is None or not verify.api:
        return StepResult(
            kind="postcondition", name="postconditions", ok=True, detail="无 api 回查(仅描述)"
        )
    method = str(verify.api.get("method", "GET"))
    path = str(resolve(verify.api.get("path", ""), context))
    status, data = await http.call(method, path, token=token)
    if status >= 400 or data is None:
        return StepResult(
            kind="postcondition",
            name="postconditions",
            ok=False,
            detail=f"回查请求失败 status={status}",
        )
    for key, expected in verify.expect.items():
        want = resolve(expected, context)
        got = dig(data, key)
        if got != want:
            return StepResult(
                kind="postcondition",
                name="postconditions",
                ok=False,
                detail=f"{key}: 期望 {want!r} 实得 {got!r}",
            )
    return StepResult(kind="postcondition", name="postconditions", ok=True, detail="回查通过")
