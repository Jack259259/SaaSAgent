"""调用信封契约测试:user_ctx 必含(红线 3 的正反例)。"""

from __future__ import annotations

from typing import Any

import pytest

from contracts.models import ToolInvocation
from contracts.validator import ContractValidationError, validate_envelope


def _valid_envelope() -> dict[str, Any]:
    return {
        "trace_id": "trace-1",
        "tool": "query_finance_data",
        "args": {"question": "华东6月执行率"},
        "user_ctx": {
            "tenant_id": "t-1",
            "user_id": "u-1",
            "roles": ["analyst"],
            "data_scope": {"regions": ["east"]},
        },
    }


def test_envelope_valid() -> None:
    validate_envelope(_valid_envelope())
    # pydantic 模型亦可解析
    ToolInvocation.model_validate(_valid_envelope())


def test_missing_user_ctx_rejected() -> None:
    env = _valid_envelope()
    del env["user_ctx"]
    with pytest.raises(ContractValidationError):
        validate_envelope(env)


def test_user_ctx_missing_tenant_rejected() -> None:
    env = _valid_envelope()
    del env["user_ctx"]["tenant_id"]
    with pytest.raises(ContractValidationError):
        validate_envelope(env)


def test_empty_roles_allowed() -> None:
    env = _valid_envelope()
    env["user_ctx"]["roles"] = []
    validate_envelope(env)  # 无角色=无权限,合法(零信任)


def test_confirmation_ok() -> None:
    env = _valid_envelope()
    env["confirmation"] = {"confirmed": True, "token": "tok-1"}
    validate_envelope(env)


def test_unknown_top_level_field_rejected() -> None:
    env = _valid_envelope()
    env["evil"] = "x"
    with pytest.raises(ContractValidationError):
        validate_envelope(env)
