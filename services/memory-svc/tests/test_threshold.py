"""写入门槛(§7.2):低重要性不入库 + 去重。"""

from __future__ import annotations

from contracts import UserCtx
from memory_svc import MemoryKind, MemoryService


def _uc() -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=["*"]
    )


async def test_low_importance_not_stored(memory: MemoryService) -> None:
    result = await memory.save_profile(_uc(), "无关紧要的随口一提", importance=0.1)
    assert result.stored is False and result.memory_id == ""
    assert await memory.search_memory(_uc(), "无关紧要", kinds=[MemoryKind.profile]) == []


async def test_dedup_skips_duplicate(memory: MemoryService) -> None:
    uc = _uc()
    first = await memory.save_profile(uc, "偏好:金额用万元", importance=0.8)
    second = await memory.save_profile(uc, "偏好:金额用万元", importance=0.8)
    assert first.stored is True
    assert second.stored is False  # 去重
