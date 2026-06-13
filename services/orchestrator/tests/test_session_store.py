"""会话存储:跨租户 / 跨用户取会话被拒(红线 9)。"""

from __future__ import annotations

import pytest

from contracts import UserCtx
from orchestrator import SessionAccessError, SessionNotFoundError, SessionStore


def _uc(tenant: str = "t1", user: str = "u1") -> UserCtx:
    return UserCtx(tenant_id=tenant, user_id=user, roles=["a"], data_scope={}, permissions=["*"])


def test_owner_can_get() -> None:
    store = SessionStore()
    s = store.create(user_ctx=_uc(), trace_id="t")
    assert store.get(s.session_id, _uc()).session_id == s.session_id


def test_cross_tenant_denied() -> None:
    store = SessionStore()
    s = store.create(user_ctx=_uc(tenant="t1"), trace_id="t")
    with pytest.raises(SessionAccessError):
        store.get(s.session_id, _uc(tenant="t2"))


def test_cross_user_denied() -> None:
    store = SessionStore()
    s = store.create(user_ctx=_uc(user="u1"), trace_id="t")
    with pytest.raises(SessionAccessError):
        store.get(s.session_id, _uc(user="u2"))


def test_unknown_session() -> None:
    store = SessionStore()
    with pytest.raises(SessionNotFoundError):
        store.get("nope", _uc())
