"""注册表 + 零信任权限(红线 3)+ 审计。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from structlog.testing import capture_logs

from contracts import ToolSpec, UserCtx
from contracts.models import ErrorCode, ResultStatus, SideEffect
from orchestrator import (
    DefaultPermissionChecker,
    NoPermissionError,
    ToolNotFoundError,
    ToolOutcome,
    ToolRegistry,
    anonymous_who,
    assert_user_ctx,
    emit_audit,
)


def _echo_spec() -> ToolSpec:
    return ToolSpec(
        name="echo_tool",
        description="回显输入(测试)",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        output_schema={"type": "object", "properties": {"echoed": {"type": "string"}}},
        permission_scope="test.echo",
        side_effects=SideEffect.read,
        confirmation_required=False,
        timeout_ms=5000,
        errors=[ErrorCode.VALIDATION_FAILED],
    )


def _user_ctx(perms: Sequence[str] = ("*",)) -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=list(perms)
    )


async def _echo_handler(args: dict[str, Any], user_ctx: UserCtx) -> ToolOutcome:
    text = str(args.get("text", ""))
    return ToolOutcome(summary=f"echoed: {text}", raw={"echoed": text})


def test_assert_user_ctx_none_raises() -> None:
    with pytest.raises(NoPermissionError):
        assert_user_ctx(None)


def test_default_checker_wildcard_and_scope() -> None:
    chk = DefaultPermissionChecker()
    spec = _echo_spec()
    chk.check(_user_ctx(perms=["*"]), spec)
    chk.check(_user_ctx(perms=["test.echo"]), spec)
    with pytest.raises(NoPermissionError):
        chk.check(_user_ctx(perms=["other.scope"]), spec)


async def test_registry_invoke_ok() -> None:
    reg = ToolRegistry()
    reg.register(_echo_spec(), _echo_handler)
    out = await reg.invoke("echo_tool", {"text": "hi"}, _user_ctx())
    assert out.summary == "echoed: hi"


async def test_registry_invoke_denied() -> None:
    reg = ToolRegistry()
    reg.register(_echo_spec(), _echo_handler)
    with pytest.raises(NoPermissionError):
        await reg.invoke("echo_tool", {"text": "x"}, _user_ctx(perms=[]))


async def test_registry_unknown_tool() -> None:
    reg = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        await reg.invoke("nope", {}, _user_ctx())


def test_emit_audit_denied_logged() -> None:
    with capture_logs() as logs:
        emit_audit(
            who=anonymous_who(),
            tool="chat",
            args_digest="sha256:0",
            result_status=ResultStatus.denied,
            trace_id="t-1",
            error_code=ErrorCode.NO_PERMISSION,
        )
    assert any(entry.get("result_status") == "denied" for entry in logs)
