"""事后反思端到端:轨迹→情景记忆 + (高分)经验入库 + 改进 JSON;低分不入库。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contracts import UserCtx
from memory_svc import MemoryKind, MemoryService
from reflection_worker import ReflectionWorker, SqliteReflectionQueue, TrajectoryRecord


def _traj(**kw: Any) -> TrajectoryRecord:
    base: dict[str, Any] = {
        "trace_id": "t-1",
        "tenant_id": "t1",
        "user_id": "u1",
        "task_signature": "月度差异分析",
        "tool_sequence": ["query_finance_data", "search_knowledge"],
    }
    base.update(kw)
    return TrajectoryRecord(**base)


def _uc() -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=["*"]
    )


async def test_high_score_stores_experience_and_episodic(tmp_path: Path) -> None:
    mem = MemoryService()
    queue = SqliteReflectionQueue()
    queue.enqueue(_traj(user_feedback="adopted", retry_count=0, final_status="completed"))
    worker = ReflectionWorker(memory_service=mem, queue=queue, improvement_dir=tmp_path)

    outcome = await worker.process_one()
    assert outcome is not None
    assert outcome.episodic_id  # 会话摘要入情景记忆
    assert outcome.experience_stored is True  # 高分 → 经验入库
    assert Path(outcome.improvement_path).is_file()  # 改进建议落盘

    hits = await mem.search_memory(_uc(), "月度差异分析", kinds=[MemoryKind.experience])
    assert hits and "月度差异分析" in hits[0].content  # 用户可检索自己的经验


async def test_low_score_skips_experience_but_keeps_episodic(tmp_path: Path) -> None:
    mem = MemoryService()
    queue = SqliteReflectionQueue()
    queue.enqueue(_traj(user_feedback="rejected", retry_count=3, final_status="failed"))
    worker = ReflectionWorker(memory_service=mem, queue=queue, improvement_dir=tmp_path)

    outcome = await worker.process_one()
    assert outcome is not None
    assert outcome.experience_stored is False  # 低分不入经验库
    assert outcome.episodic_id  # 情景摘要仍入库
    assert await mem.search_memory(_uc(), "月度差异分析", kinds=[MemoryKind.experience]) == []


async def test_empty_queue_returns_none(tmp_path: Path) -> None:
    worker = ReflectionWorker(
        memory_service=MemoryService(), queue=SqliteReflectionQueue(), improvement_dir=tmp_path
    )
    assert await worker.process_one() is None
