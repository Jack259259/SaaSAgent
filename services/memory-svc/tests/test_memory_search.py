"""向量检索 TopK + 经验仅 reflection-worker 可录。"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from contracts import UserCtx
from memory_svc import ExperienceEntry, MemoryKind, MemoryService


def _uc(roles: Sequence[str] = ("analyst",)) -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=list(roles), data_scope={}, permissions=["*"]
    )


async def test_search_returns_relevant_topk(memory: MemoryService) -> None:
    uc = _uc()
    await memory.save_episodic(uc, "讨论了资金计划执行率口径", importance=0.8)
    await memory.save_episodic(uc, "讨论了报表导出的格式偏好", importance=0.8)
    hits = await memory.search_memory(uc, "执行率", top_k=1)
    assert len(hits) == 1
    assert "执行率" in hits[0].content


async def test_record_experience_requires_reflection_role(memory: MemoryService) -> None:
    entry = ExperienceEntry(
        task_signature="月度差异分析", applicability="月度对账", effective_path="取数→对比→下钻"
    )
    with pytest.raises(PermissionError):
        await memory.record_experience(_uc(roles=["analyst"]), entry)

    reflector = _uc(roles=["reflection_worker"])
    result = await memory.record_experience(reflector, entry)
    assert result.stored is True
    hits = await memory.search_memory(reflector, "月度差异分析", kinds=[MemoryKind.experience])
    assert hits and "月度差异分析" in hits[0].content
