"""e2e:写步骤确认往返。段1 → confirm_request(暂停)→ /chat/confirm → 段2 → done。"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_gateway import deps
from agent_gateway.app import app
from contracts import ToolSpec
from contracts.models import ErrorCode, SideEffect
from llm import Message, MockProvider, ScriptedTurn, TextBlock, ToolUseBlock
from orchestrator import SessionStore, ToolContext, ToolOutcome, ToolRegistry

_HDR = json.dumps(
    {"tenant_id": "t1", "user_id": "u1", "roles": ["a"], "data_scope": {}, "permissions": ["*"]}
)


def _echo_spec() -> ToolSpec:
    return ToolSpec(
        name="echo_tool",
        description="回显(测试)",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        permission_scope="test.echo",
        side_effects=SideEffect.read,
        confirmation_required=False,
        timeout_ms=5000,
        errors=[ErrorCode.VALIDATION_FAILED],
    )


async def _echo(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    return ToolOutcome(summary="echoed", raw={"ok": True})


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(_echo_spec(), _echo)
    return reg


def _last_text(messages: Sequence[Message]) -> str:
    return " ".join(b.text for b in messages[-1].content if isinstance(b, TextBlock))


def _router(messages: Sequence[Message]) -> ScriptedTurn:
    last = _last_text(messages)
    if "请综合" in last:
        return ScriptedTurn(text="写操作已完成", stop_reason="end_turn")
    if "执行步骤 w1" in last:
        return ScriptedTurn(
            tool_calls=[ToolUseBlock(id="e", name="echo_tool", input={})], stop_reason="tool_use"
        )
    return ScriptedTurn(
        tool_calls=[
            ToolUseBlock(
                id="p",
                name="update_plan",
                input={"steps": [{"id": "w1", "goal": "提交计划(写)", "needs_confirmation": True}]},
            )
        ],
        stop_reason="tool_use",
    )


def _parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        etype, data = "", "{}"
        for line in block.splitlines():
            if line.startswith("event: "):
                etype = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        out.append((etype, json.loads(data)))
    return out


@pytest.fixture(autouse=True)
def _overrides() -> Iterator[None]:
    store = SessionStore()
    app.dependency_overrides[deps.get_provider] = lambda: MockProvider(router=_router)
    app.dependency_overrides[deps.get_registry] = _registry
    app.dependency_overrides[deps.get_session_store] = lambda: store
    yield
    app.dependency_overrides.clear()


def test_confirm_round_trip() -> None:
    client = TestClient(app)
    with client.stream(
        "POST", "/chat", headers={"X-User-Ctx": _HDR}, json={"message": "帮我提交计划"}
    ) as resp:
        assert resp.status_code == 200
        session_id = resp.headers["X-Session-Id"]
        seg1 = _parse_sse("".join(resp.iter_text()))
    types1 = [t for t, _ in seg1]
    assert "plan" in types1
    assert "confirm_request" in types1
    assert "done" not in types1  # 暂停,本段未完成

    with client.stream(
        "POST",
        "/chat/confirm",
        headers={"X-User-Ctx": _HDR},
        json={"session_id": session_id, "confirmation": {"confirmed": True}},
    ) as resp2:
        assert resp2.status_code == 200
        seg2 = _parse_sse("".join(resp2.iter_text()))
    types2 = [t for t, _ in seg2]
    assert "tool_call" in types2
    assert types2[-1] == "done"
    by_type = {t: d for t, d in seg2}
    assert by_type["done"]["stop_reason"] == "completed"


def test_confirm_cross_user_denied() -> None:
    client = TestClient(app)
    with client.stream(
        "POST", "/chat", headers={"X-User-Ctx": _HDR}, json={"message": "帮我提交计划"}
    ) as resp:
        session_id = resp.headers["X-Session-Id"]
        list(resp.iter_text())
    other = json.dumps(
        {"tenant_id": "t1", "user_id": "u2", "roles": ["a"], "data_scope": {}, "permissions": ["*"]}
    )
    resp2 = client.post(
        "/chat/confirm",
        headers={"X-User-Ctx": other},
        json={"session_id": session_id, "confirmation": {"confirmed": True}},
    )
    assert resp2.status_code == 403  # 红线 9:跨用户取会话被拒
