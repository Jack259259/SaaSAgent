"""红线 3:缺 user_ctx 一律拒(全工具矩阵契约闸);越权调用运行时二次校验拒绝并记审计。

- 契约层:对每一份工具规格,删去信封 user_ctx → validate_envelope 拒绝(零信任前置闸)。
- 运行时层:注册表对每个基础工具二次校验 permission_scope,无权即 NoPermissionError。
- 审计:经编排器的越权调用产生 result_status=denied / error_code=NO_PERMISSION 审计事件。
"""

from __future__ import annotations

from typing import Any

import pytest
from structlog.testing import capture_logs

from contracts import UserCtx
from contracts.loader import load_toolspecs
from contracts.validator import ContractValidationError, validate_envelope
from llm import MockProvider, ScriptedTurn, ToolUseBlock
from orchestrator import Orchestrator, Session, ToolContext, ToolRegistry, base_tool_handlers
from orchestrator.permissions import NoPermissionError
from orchestrator.workspace import Workspace


def _envelope(tool: str) -> dict[str, Any]:
    return {
        "trace_id": "trace-sec",
        "tool": tool,
        "args": {},
        "user_ctx": {"tenant_id": "t1", "user_id": "u", "roles": ["analyst"], "data_scope": {}},
    }


def test_every_tool_envelope_without_user_ctx_rejected() -> None:
    specs = [ls.spec for ls in load_toolspecs()]
    assert len(specs) >= 20  # 全工具矩阵(5 领域 + 18 基础)
    for spec in specs:
        env = _envelope(spec.name)
        del env["user_ctx"]
        with pytest.raises(ContractValidationError):
            validate_envelope(env)  # 缺 user_ctx → 契约层拒绝


def _noperm_ctx() -> ToolContext:
    uc = UserCtx(tenant_id="t1", user_id="u", roles=["analyst"], data_scope={})  # permissions=[]
    return ToolContext(user_ctx=uc, workspace=Workspace(), trace_id="t-sec")


async def test_registry_denies_every_base_tool_without_permission() -> None:
    registry = ToolRegistry()
    registry.register_from_contracts(base_tool_handlers())
    ctx = _noperm_ctx()
    assert registry.specs()
    for spec in registry.specs():
        with pytest.raises(NoPermissionError):
            await registry.invoke(spec.name, {}, ctx)  # 二次校验:无权即拒


async def test_denied_call_is_audited() -> None:
    registry = ToolRegistry()
    registry.register_from_contracts(base_tool_handlers())
    provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="x", name="read_workspace", input={"ref": "r"})],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text="(无权限,已停止)", stop_reason="end_turn"),
        ]
    )
    orch = Orchestrator(provider=provider, registry=registry)
    uc = UserCtx(tenant_id="t1", user_id="u", roles=["analyst"], data_scope={})  # 无权限
    session = Session(session_id="s", trace_id="t-aud", user_ctx=uc)
    orch.seed_user_message(session, "读工作区")
    with capture_logs() as logs:
        [e async for e in orch.advance(session)]
    audits = [e for e in logs if e.get("event") == "tool_audit"]
    assert any(
        a.get("result_status") == "denied" and a.get("error_code") == "NO_PERMISSION"
        for a in audits
    )
