"""审计事件契约测试:正反例 + 跨文件 $ref(error_code 复用 toolspec 枚举)。"""

from __future__ import annotations

from typing import Any

import pytest

from contracts.models import AuditEvent
from contracts.validator import ContractValidationError, validate_audit


def _valid_audit() -> dict[str, Any]:
    return {
        "who": {"tenant_id": "t-1", "user_id": "u-1", "roles": ["analyst"]},
        "tool": "query_finance_data",
        "args_digest": "sha256:abcd1234",
        "result_status": "ok",
        "trace_id": "t-1",
        "ts": "2026-06-13T08:00:00Z",
    }


def test_audit_valid() -> None:
    validate_audit(_valid_audit())
    AuditEvent.model_validate(_valid_audit())


def test_valid_error_code_via_cross_ref() -> None:
    # 证明 audit.json 的 $ref → urn:zijin:toolspec#/$defs/errorCode 被注册表解析且接受合法值
    ev = _valid_audit()
    ev["result_status"] = "error"
    ev["error_code"] = "NO_PERMISSION"
    validate_audit(ev)


def test_invalid_error_code_rejected() -> None:
    ev = _valid_audit()
    ev["error_code"] = "NOPE"
    with pytest.raises(ContractValidationError):
        validate_audit(ev)


def test_bad_result_status_rejected() -> None:
    ev = _valid_audit()
    ev["result_status"] = "success"
    with pytest.raises(ContractValidationError):
        validate_audit(ev)


def test_missing_args_digest_rejected() -> None:
    ev = _valid_audit()
    del ev["args_digest"]
    with pytest.raises(ContractValidationError):
        validate_audit(ev)
