"""SOP 状态机:执行→暂停→确认→完成→postcondition;及失败负例(postcondition/precondition/步骤)。"""

from __future__ import annotations

import httpx
import pytest

from contracts import UserCtx
from sop_executor import (
    FakeUiRunner,
    HttpCaller,
    RunAccessError,
    RunStatus,
    Sop,
    SopExecutor,
)
from sop_executor.demo_mock import DemoMockApp


def _caller(app: DemoMockApp) -> HttpCaller:
    return HttpCaller(
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock")
    )


def _uc(perms: list[str]) -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["internal"], data_scope={}, permissions=perms
    )


def _executor(app: DemoMockApp) -> SopExecutor:
    return SopExecutor(http=_caller(app), ui_runner=FakeUiRunner())


async def test_full_cycle_pause_confirm_succeed(demo_sop: Sop) -> None:
    ex = _executor(DemoMockApp())
    uc = _uc(["sop.write.run"])
    state = await ex.submit(demo_sop, {"name": "x", "amount": 10}, uc)
    assert state.status == RunStatus.paused  # confirm 步暂停
    assert state.pending_confirm is not None and state.pending_confirm.action_preview

    final = await ex.resume(state, demo_sop, confirmed=True, user_ctx=uc)
    assert final.status == RunStatus.succeeded
    assert any(s.kind == "api" and s.ok for s in final.steps)
    assert any(s.kind == "postcondition" and s.ok for s in final.steps)


async def test_postcondition_failure_is_failed_not_succeeded(demo_sop: Sop) -> None:
    ex = _executor(DemoMockApp(created_status="draft"))  # 回查得 draft,期望 created
    uc = _uc(["*"])
    state = await ex.submit(demo_sop, {"name": "x", "amount": 10}, uc)
    final = await ex.resume(state, demo_sop, confirmed=True, user_ctx=uc)
    assert final.status == RunStatus.failed  # 绝不报成功
    assert any(s.kind == "postcondition" and not s.ok for s in final.steps)


async def test_precondition_permission_denied(demo_sop: Sop) -> None:
    ex = _executor(DemoMockApp())
    state = await ex.submit(demo_sop, {"name": "x", "amount": 10}, _uc(["other.perm"]))
    assert state.status == RunStatus.failed
    assert state.steps[0].kind == "precondition" and not state.steps[0].ok


async def test_reject_confirmation_fails(demo_sop: Sop) -> None:
    ex = _executor(DemoMockApp())
    uc = _uc(["*"])
    state = await ex.submit(demo_sop, {"name": "x", "amount": 10}, uc)
    final = await ex.resume(state, demo_sop, confirmed=False, user_ctx=uc)
    assert final.status == RunStatus.failed


async def test_api_step_failure_uses_on_failure_hint(demo_sop: Sop) -> None:
    ex = _executor(DemoMockApp(post_status=409))  # POST 冲突
    uc = _uc(["*"])
    state = await ex.submit(demo_sop, {"name": "x", "amount": 10}, uc)
    final = await ex.resume(state, demo_sop, confirmed=True, user_ctx=uc)
    assert final.status == RunStatus.failed
    assert (
        final.failure_hint == "同名条目已存在,请换个名称后重试"
    )  # 命中 on_failure when=status=409
    assert not any(s.kind == "postcondition" for s in final.steps)  # 不跳步:失败即停,未做回查


async def test_resume_cross_tenant_rejected(demo_sop: Sop) -> None:
    # 零信任:他租户/他用户不得 resume 别人的 run(红线 3/9)。
    ex = _executor(DemoMockApp())
    owner = _uc(["*"])  # tenant_id=t1, user_id=u1
    state = await ex.submit(demo_sop, {"name": "x", "amount": 10}, owner)
    assert state.status == RunStatus.paused
    intruder = UserCtx(
        tenant_id="t2", user_id="evil", roles=["internal"], data_scope={}, permissions=["*"]
    )
    with pytest.raises(RunAccessError):
        await ex.resume(state, demo_sop, confirmed=True, user_ctx=intruder)
