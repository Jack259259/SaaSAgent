"""转人工:工单落 JSON、上下文打包、按接收方权限脱敏。"""

from __future__ import annotations

import json
from pathlib import Path

from contracts import UserCtx
from scheduler_svc import EscalationService, FileTicketGateway


def _uc() -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=["*"]
    )


def test_ticket_written_and_redacted_for_default_recipient(tmp_path: Path) -> None:
    svc = EscalationService(gateway=FileTicketGateway(tmp_path))
    ticket = svc.escalate(
        _uc(), summary="客户问题,联系 13800138000", context_refs=["ws://chat/1"], priority="high"
    )
    assert (
        "13800138000" not in ticket.summary and "138****8000" in ticket.summary
    )  # 非内部接收方脱敏
    assert ticket.context_refs == ["ws://chat/1"] and ticket.priority == "high"
    written = json.loads((tmp_path / f"{ticket.ticket_id}.json").read_text("utf-8"))
    assert written["summary"] == ticket.summary and written["tenant_id"] == "t1"


def test_privileged_recipient_sees_full(tmp_path: Path) -> None:
    svc = EscalationService(gateway=FileTicketGateway(tmp_path))
    ticket = svc.escalate(_uc(), summary="联系 13800138000", recipient_roles=("internal_support",))
    assert "13800138000" in ticket.summary  # 内部接收方看全量
