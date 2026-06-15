"""红线 4:对业务系统的写仅经 sop-executor,且必须用户确认(orchestrator 闸 + executor 复验,双闸)。

run_sop 命中 confirm 步即暂停,不会在未确认时写;拒绝确认 → SOP 失败,写未提交;
经编排器调用时强制发 confirm_request 并暂停,不自动完成写。
"""

from __future__ import annotations

from pathlib import Path

import httpx

from contracts import UserCtx
from llm import MockProvider, ScriptedTurn, ToolUseBlock
from orchestrator import (
    ConfirmRequestEvent,
    DoneEvent,
    Orchestrator,
    Session,
    ToolContext,
    ToolRegistry,
)
from orchestrator.tools import make_run_sop_handler
from orchestrator.workspace import Workspace
from sop_executor import HttpCaller, SopService
from sop_executor.demo_mock import DemoMockApp

_ASSETS_SOPS = Path(__file__).parents[2] / "assets" / "sops"
_RUN_ARGS = {"sop_id": "demo.create-item", "inputs": {"name": "x", "amount": 10}}


def _service() -> SopService:
    caller = HttpCaller(
        httpx.AsyncClient(transport=httpx.ASGITransport(app=DemoMockApp()), base_url="http://mock")
    )
    return SopService.open(sops_dir=_ASSETS_SOPS, http=caller)


def _uc() -> UserCtx:
    return UserCtx(
        tenant_id="t1",
        user_id="u1",
        roles=["internal"],
        data_scope={},
        permissions=["sop.write.run"],
    )


def _ctx() -> ToolContext:
    return ToolContext(user_ctx=_uc(), workspace=Workspace(), trace_id="t-wg")


async def test_run_sop_submit_pauses_and_does_not_write() -> None:
    run_handler, _ = make_run_sop_handler(_service())
    outcome = await run_handler(_RUN_ARGS, _ctx())
    assert outcome.confirmation is not None  # 命中 confirm 步 → 暂停
    assert outcome.raw["status"] != "succeeded"  # 未确认 → 写未发生


async def test_rejected_confirmation_does_not_write() -> None:
    run_handler, run_resume = make_run_sop_handler(_service())
    ctx = _ctx()
    outcome = await run_handler(_RUN_ARGS, ctx)
    assert outcome.confirmation is not None
    rejected = await run_resume(outcome.confirmation.token, False, ctx)  # 拒绝确认
    assert rejected.is_error  # 写未提交,SOP 失败


async def test_orchestrator_gates_write_until_confirmed() -> None:
    registry = ToolRegistry()
    run_handler, run_resume = make_run_sop_handler(_service())
    registry.register_from_contracts({"run_sop": run_handler}, resumes={"run_sop": run_resume})
    provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="r", name="run_sop", input=_RUN_ARGS)],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text="(等待确认)", stop_reason="end_turn"),
        ]
    )
    orch = Orchestrator(provider=provider, registry=registry)
    session = Session(session_id="s", trace_id="t-wg", user_ctx=_uc())
    orch.seed_user_message(session, "执行写操作")
    seg = [e async for e in orch.advance(session)]
    assert any(isinstance(e, ConfirmRequestEvent) for e in seg)  # 强制确认
    assert not any(isinstance(e, DoneEvent) for e in seg)  # 写未自动完成
    assert session.pending is not None and session.pending.kind == "tool_confirm"
