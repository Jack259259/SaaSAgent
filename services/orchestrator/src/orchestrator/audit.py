"""结构化审计(§9.2 / 红线 4)。每次工具调用与拒绝都发审计事件。

禁止记录入参原文、密钥、token、SQL 结果明细(§6):args 仅以脱敏摘要(args_digest)记录。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import structlog

from contracts import AuditEvent, UserCtx
from contracts.models import AuditWho, ErrorCode, ResultStatus

_logger = structlog.get_logger("audit")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def digest_args(args: dict[str, Any]) -> str:
    """入参脱敏摘要(稳定哈希,不含原文)。"""
    blob = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def who_from_user_ctx(user_ctx: UserCtx) -> AuditWho:
    return AuditWho(
        tenant_id=user_ctx.tenant_id, user_id=user_ctx.user_id, roles=list(user_ctx.roles)
    )


def anonymous_who() -> AuditWho:
    """未鉴权请求(无 user_ctx)的审计主体哨兵。"""
    return AuditWho(tenant_id="-", user_id="-", roles=[])


def emit_audit(
    *,
    who: AuditWho,
    tool: str,
    args_digest: str,
    result_status: ResultStatus,
    trace_id: str,
    ts: str | None = None,
    error_code: ErrorCode | None = None,
    latency_ms: int | None = None,
) -> AuditEvent:
    event = AuditEvent(
        who=who,
        tool=tool,
        args_digest=args_digest,
        result_status=result_status,
        trace_id=trace_id,
        ts=ts or _now_iso(),
        error_code=error_code,
        latency_ms=latency_ms,
    )
    _logger.info("tool_audit", **event.model_dump(mode="json", exclude_none=True))
    return event
