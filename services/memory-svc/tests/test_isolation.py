"""租户/用户隔离(红线 9):A 的记忆 B 搜不到。"""

from __future__ import annotations

from collections.abc import Sequence

from contracts import UserCtx
from memory_svc import MemoryService


def _uc(tenant: str = "t1", user: str = "u1", roles: Sequence[str] = ()) -> UserCtx:
    return UserCtx(
        tenant_id=tenant, user_id=user, roles=list(roles), data_scope={}, permissions=["*"]
    )


async def test_cross_tenant_invisible(memory: MemoryService) -> None:
    a = _uc("t1", "ua")
    b = _uc("t2", "ub")
    await memory.save_episodic(a, "用户A讨论了执行率口径", importance=0.8)
    assert await memory.search_memory(b, "执行率口径") == []  # 跨租户搜不到
    assert len(await memory.search_memory(a, "执行率口径")) >= 1  # 本人可搜到


async def test_cross_user_same_tenant_invisible(memory: MemoryService) -> None:
    a = _uc("t1", "ua")
    other = _uc("t1", "ub")  # 同租户不同用户
    await memory.save_episodic(a, "A的私有会话摘要", importance=0.8)
    assert await memory.search_memory(other, "私有会话") == []  # 跨用户也不可见
