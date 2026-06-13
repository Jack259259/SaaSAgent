"""AgentState 契约测试:正反例 + pydantic 模型解析(方案 §4.2)。"""

from __future__ import annotations

from typing import Any

import pytest

from contracts.models import AgentState
from contracts.validator import ContractValidationError, validate_agent_state


def _valid_state() -> dict[str, Any]:
    return {
        "ids": {"session_id": "s-1", "trace_id": "t-1", "tenant_id": "t-1", "user_id": "u-1"},
        "user_ctx": {"roles": ["analyst"], "data_scope": {}},
        "mode": "react",
        "messages": [],
        "plan": {
            "version": 0,
            "steps": [{"id": "s1", "goal": "取数", "status": "pending", "capability_hint": "data"}],
        },
        "workspace": {"items": []},
        "budget": {"max_steps": 10, "max_cost": 1.0, "used_steps": 0, "used_cost": 0.0},
        "reflection": {"inline_retries": 0, "verdicts": []},
    }


def test_agent_state_valid() -> None:
    validate_agent_state(_valid_state())
    AgentState.model_validate(_valid_state())


def test_bad_mode_rejected() -> None:
    state = _valid_state()
    state["mode"] = "freestyle"
    with pytest.raises(ContractValidationError):
        validate_agent_state(state)


def test_bad_step_status_rejected() -> None:
    state = _valid_state()
    state["plan"]["steps"][0]["status"] = "weird"
    with pytest.raises(ContractValidationError):
        validate_agent_state(state)


def test_bad_workspace_item_type_rejected() -> None:
    state = _valid_state()
    state["workspace"]["items"] = [{"key": "k", "type": "not_a_type", "ref": "r", "summary": "s"}]
    with pytest.raises(ContractValidationError):
        validate_agent_state(state)


def test_missing_budget_rejected() -> None:
    state = _valid_state()
    del state["budget"]
    with pytest.raises(ContractValidationError):
        validate_agent_state(state)
