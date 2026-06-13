"""e2e:MockProvider 回放"调 echo_tool 再作答" → SSE 依次 tool_call / tool_result_summary /
answer_delta / done(阶段 2 验收核心)。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_gateway import deps
from agent_gateway.app import app
from contracts import ToolSpec, UserCtx
from contracts.models import ErrorCode, SideEffect
from llm import MockProvider, ScriptedTurn, ToolUseBlock
from orchestrator import ToolOutcome, ToolRegistry


def _echo_spec() -> ToolSpec:
    return ToolSpec(
        name="echo_tool",
        description="回显输入(测试)",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        output_schema={"type": "object"},
        permission_scope="test.echo",
        side_effects=SideEffect.read,
        confirmation_required=False,
        timeout_ms=5000,
        errors=[ErrorCode.VALIDATION_FAILED],
    )


async def _echo_handler(args: dict[str, Any], user_ctx: UserCtx) -> ToolOutcome:
    text = str(args.get("text", ""))
    return ToolOutcome(summary=f"echoed: {text}", raw={"echoed": text})


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(_echo_spec(), _echo_handler)
    return reg


def _user_ctx_header() -> str:
    return json.dumps(
        {
            "tenant_id": "t1",
            "user_id": "u1",
            "roles": ["analyst"],
            "data_scope": {},
            "permissions": ["*"],
        }
    )


def _parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        etype = ""
        data = "{}"
        for line in block.splitlines():
            if line.startswith("event: "):
                etype = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        out.append((etype, json.loads(data)))
    return out


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def test_chat_streams_tool_then_answer() -> None:
    turns = [
        ScriptedTurn(
            text="我来回显",
            tool_calls=[ToolUseBlock(id="c1", name="echo_tool", input={"text": "hi"})],
            stop_reason="tool_use",
        ),
        ScriptedTurn(text="结果是 hi", stop_reason="end_turn"),
    ]
    app.dependency_overrides[deps.get_provider] = lambda: MockProvider(turns)
    app.dependency_overrides[deps.get_registry] = _registry

    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat",
        headers={"X-User-Ctx": _user_ctx_header()},
        json={"message": "回显 hi"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        text = "".join(resp.iter_text())

    events = _parse_sse(text)
    types = [t for t, _ in events]
    assert "tool_call" in types
    assert "tool_result_summary" in types
    assert "answer_delta" in types
    assert types[-1] == "done"
    # 顺序:tool_call → tool_result_summary → answer_delta → done
    assert (
        types.index("tool_call")
        < types.index("tool_result_summary")
        < types.index("answer_delta")
        < types.index("done")
    )

    by_type = {t: d for t, d in events}
    assert by_type["tool_call"]["tool"] == "echo_tool"
    assert by_type["tool_result_summary"]["summary"] == "echoed: hi"
    assert by_type["tool_result_summary"]["workspace_ref"].startswith("ws://")
    answer = "".join(d["text"] for t, d in events if t == "answer_delta")
    assert answer == "结果是 hi"
    assert by_type["done"]["stop_reason"] == "end_turn"
