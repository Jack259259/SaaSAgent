"""e2e:ask_user 往返。段1 → ask_user(暂停)→ /chat/confirm(answers)→ 段2 → done。"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_gateway import deps
from agent_gateway.app import app
from llm import Message, MockProvider, ScriptedTurn, TextBlock, ToolResultBlock, ToolUseBlock
from orchestrator import SessionStore, ToolRegistry

_HDR = json.dumps(
    {"tenant_id": "t1", "user_id": "u1", "roles": ["a"], "data_scope": {}, "permissions": ["*"]}
)


def _all_text(messages: Sequence[Message]) -> str:
    parts: list[str] = []
    for m in messages:
        for b in m.content:
            if isinstance(b, TextBlock):
                parts.append(b.text)
            elif isinstance(b, ToolResultBlock):
                parts.append(b.content)
    return " ".join(parts)


def _router(messages: Sequence[Message]) -> ScriptedTurn:
    # 一旦答案(含在途)回流到消息里,就给出最终回答;否则先澄清。
    if "含在途" in _all_text(messages):
        return ScriptedTurn(text="按『含在途』口径,执行率为 92%。", stop_reason="end_turn")
    return ScriptedTurn(
        tool_calls=[
            ToolUseBlock(
                id="ask",
                name="ask_user",
                input={
                    "questions": [{"question": "用哪个口径?", "options": ["含在途", "不含在途"]}]
                },
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
    app.dependency_overrides[deps.get_registry] = lambda: ToolRegistry()
    app.dependency_overrides[deps.get_session_store] = lambda: store
    yield
    app.dependency_overrides.clear()


def test_ask_user_round_trip() -> None:
    client = TestClient(app)
    with client.stream(
        "POST", "/chat", headers={"X-User-Ctx": _HDR}, json={"message": "6月执行率是多少?"}
    ) as resp:
        assert resp.status_code == 200
        session_id = resp.headers["X-Session-Id"]
        seg1 = _parse_sse("".join(resp.iter_text()))
    types1 = [t for t, _ in seg1]
    assert "ask_user" in types1
    assert "done" not in types1
    ask = next(d for t, d in seg1 if t == "ask_user")
    assert ask["questions"][0]["options"] == ["含在途", "不含在途"]

    with client.stream(
        "POST",
        "/chat/confirm",
        headers={"X-User-Ctx": _HDR},
        json={"session_id": session_id, "answers": {"q0": "含在途"}},
    ) as resp2:
        assert resp2.status_code == 200
        seg2 = _parse_sse("".join(resp2.iter_text()))
    answer = "".join(d["text"] for t, d in seg2 if t == "answer_delta")
    assert "92%" in answer
    assert [t for t, _ in seg2][-1] == "done"
