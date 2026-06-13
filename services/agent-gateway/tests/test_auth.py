"""鉴权负例(红线 3):无 user_ctx → 401 + 审计;非法 → 403。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_gateway import deps
from agent_gateway.app import app
from contracts.models import ResultStatus
from llm import MockProvider, ScriptedTurn
from orchestrator import ToolRegistry


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    app.dependency_overrides[deps.get_provider] = lambda: MockProvider([ScriptedTurn(text="x")])
    app.dependency_overrides[deps.get_registry] = lambda: ToolRegistry()
    yield
    app.dependency_overrides.clear()


def test_missing_user_ctx_returns_401_and_audits(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def spy(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr("agent_gateway.auth.emit_audit", spy)
    client = TestClient(app)
    resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 401
    assert any(c.get("result_status") == ResultStatus.denied for c in calls)


def test_invalid_json_user_ctx_returns_403() -> None:
    client = TestClient(app)
    resp = client.post("/chat", headers={"X-User-Ctx": "not-json"}, json={"message": "hi"})
    assert resp.status_code == 403


def test_malformed_user_ctx_returns_403() -> None:
    client = TestClient(app)
    # 合法 JSON 但缺必填字段(user_id / roles / data_scope)
    resp = client.post(
        "/chat",
        headers={"X-User-Ctx": json.dumps({"tenant_id": "t"})},
        json={"message": "hi"},
    )
    assert resp.status_code == 403
