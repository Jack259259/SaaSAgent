"""find_sop / run_sop 经编排器全链:run_sop→tool_confirm 暂停→resume→succeeded(红线 4 双闸)。"""

from __future__ import annotations

from pathlib import Path

import httpx

from contracts import UserCtx
from llm import Message, MockProvider, Role, ScriptedTurn, TextBlock, ToolUseBlock
from orchestrator import (
    ConfirmRequestEvent,
    DoneEvent,
    Orchestrator,
    Session,
    ToolRegistry,
    ToolResultSummaryEvent,
)
from orchestrator.tools import make_find_sop_handler, make_run_sop_handler
from sop_executor import HttpCaller, SopService
from sop_executor.demo_mock import DemoMockApp

_ASSETS_SOPS = Path(__file__).parents[3] / "assets" / "sops"


def _service(app: DemoMockApp | None = None) -> SopService:
    caller = HttpCaller(
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app or DemoMockApp()), base_url="http://mock"
        )
    )
    return SopService.open(sops_dir=_ASSETS_SOPS, http=caller)


def _registry(svc: SopService) -> ToolRegistry:
    reg = ToolRegistry()
    run_handler, run_resume = make_run_sop_handler(svc)
    reg.register_from_contracts(
        {"find_sop": make_find_sop_handler(svc), "run_sop": run_handler},
        resumes={"run_sop": run_resume},
    )
    return reg


def _session() -> Session:
    uc = UserCtx(
        tenant_id="t1",
        user_id="u1",
        roles=["internal"],
        data_scope={},
        permissions=["sop.write.run", "sop.read.find"],
    )
    s = Session(session_id="s-sop", trace_id="t-sop", user_ctx=uc)
    s.messages.append(Message(role=Role.user, content=[TextBlock("帮我新建一个条目")]))
    return s


def _run_call() -> ToolUseBlock:
    return ToolUseBlock(
        id="r1",
        name="run_sop",
        input={"sop_id": "demo.create-item", "inputs": {"name": "x", "amount": 10}},
    )


async def test_run_sop_confirm_cycle_succeeds() -> None:
    provider = MockProvider(
        [
            ScriptedTurn(tool_calls=[_run_call()], stop_reason="tool_use"),
            ScriptedTurn(text="条目已创建并核验通过", stop_reason="end_turn"),
        ]
    )
    orch = Orchestrator(provider=provider, registry=_registry(_service()))
    session = _session()

    seg1 = [e async for e in orch.advance(session)]
    assert any(isinstance(e, ConfirmRequestEvent) for e in seg1)  # confirm_request 发出
    assert session.pending is not None and session.pending.kind == "tool_confirm"
    assert not any(isinstance(e, DoneEvent) for e in seg1)

    seg2 = [e async for e in orch.resume(session, confirmation={"confirmed": True})]
    summaries = [e for e in seg2 if isinstance(e, ToolResultSummaryEvent)]
    assert any("成功" in e.summary for e in summaries)  # SOP 执行成功
    done = [e for e in seg2 if isinstance(e, DoneEvent)]
    assert done[-1].stop_reason == "end_turn"
    assert session.pending is None


async def test_run_sop_confirm_rejected_fails() -> None:
    provider = MockProvider(
        [
            ScriptedTurn(tool_calls=[_run_call()], stop_reason="tool_use"),
            ScriptedTurn(text="已取消", stop_reason="end_turn"),
        ]
    )
    orch = Orchestrator(provider=provider, registry=_registry(_service()))
    session = _session()
    [e async for e in orch.advance(session)]
    seg2 = [e async for e in orch.resume(session, confirmation={"confirmed": False})]
    summaries = [e for e in seg2 if isinstance(e, ToolResultSummaryEvent)]
    assert any("失败" in e.summary for e in summaries)  # 拒绝确认 → 失败,不报成功


async def test_find_sop_tool() -> None:
    provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="f1", name="find_sop", input={"query": "创建条目"})],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text="为你找到相关 SOP", stop_reason="end_turn"),
        ]
    )
    orch = Orchestrator(provider=provider, registry=_registry(_service()))
    events = [e async for e in orch.advance(_session())]
    summaries = [e for e in events if isinstance(e, ToolResultSummaryEvent)]
    assert any("找到" in e.summary for e in summaries)
