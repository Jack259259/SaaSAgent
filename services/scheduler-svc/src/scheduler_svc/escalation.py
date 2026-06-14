"""转人工(方案 §5.5):生成工单 + 上下文移交,移交内容按接收方权限脱敏(助手域写)。"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from contracts import UserCtx

from .models import Ticket

_DEFAULT_TICKETS_DIR = Path("docs/ops/tickets")
_PRIVILEGED_ROLES = {"internal", "internal_support", "internal_dev"}
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
_AMOUNT_RE = re.compile(r"[¥￥]\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:亿元|万元|元)")


def _redact(text: str) -> str:
    text = _PHONE_RE.sub(r"\1****\2", text)
    return _AMOUNT_RE.sub("[金额]", text)


class TicketGateway(Protocol):
    def create(self, ticket: Ticket) -> None: ...


class FileTicketGateway:
    """桩实现:工单落 docs/ops/tickets/<id>.json(目录可注入;运行产物不入库)。"""

    def __init__(self, tickets_dir: Path = _DEFAULT_TICKETS_DIR) -> None:
        self._dir = tickets_dir

    def create(self, ticket: Ticket) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / f"{ticket.ticket_id}.json").write_text(
            json.dumps(ticket.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )


class EscalationService:
    def __init__(self, *, gateway: TicketGateway | None = None) -> None:
        self._gateway = gateway or FileTicketGateway()

    def escalate(
        self,
        user_ctx: UserCtx,
        *,
        summary: str,
        context_refs: list[str] | None = None,
        priority: str = "normal",
        recipient_roles: tuple[str, ...] = (),
    ) -> Ticket:
        # 按接收方权限脱敏:接收方非内部角色 → 脱敏移交内容(脱敏钩子)。
        privileged = bool(set(recipient_roles) & _PRIVILEGED_ROLES)
        ticket = Ticket(
            ticket_id=uuid.uuid4().hex,
            tenant_id=user_ctx.tenant_id,
            user_id=user_ctx.user_id,
            summary=summary if privileged else _redact(summary),
            context_refs=list(context_refs or []),
            priority=priority,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._gateway.create(ticket)
        return ticket
