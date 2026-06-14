"""事后反思作业(方案 §8.2)。消费任务终态 → 三件套:

1. 会话摘要 → 情景记忆(memory_svc.save_episodic);
2. 经验条目 → **启发式评分过阈** → 经验库(memory_svc.record_experience,reflection_worker 角色;
   这是经验入库的唯一路径,呼应 9a;**绕过评分=禁止**);
3. 改进建议 → docs/ops/improvement-queue/<id>.json。
所有写入产生审计(structlog)。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import structlog

from contracts import UserCtx
from memory_svc import ExperienceEntry, MemoryService

from .models import ReflectionOutcome, TrajectoryRecord
from .queue import ReflectionQueue
from .scoring import EXPERIENCE_THRESHOLD, score_trajectory

_REFLECTION_ROLE = "reflection_worker"
_DEFAULT_IMPROVEMENT_DIR = Path("docs/ops/improvement-queue")
_log = structlog.get_logger("reflection_worker")


class ReflectionWorker:
    def __init__(
        self,
        *,
        memory_service: MemoryService,
        queue: ReflectionQueue,
        improvement_dir: Path = _DEFAULT_IMPROVEMENT_DIR,
    ) -> None:
        self._memory = memory_service
        self._queue = queue
        self._improvement_dir = improvement_dir

    async def process_one(self) -> ReflectionOutcome | None:
        trajectory = self._queue.dequeue()
        if trajectory is None:
            return None
        return await self._reflect(trajectory)

    async def _reflect(self, traj: TrajectoryRecord) -> ReflectionOutcome:
        # reflection-worker 身份:落在轨迹所属 (tenant, user) 的记忆分区 + reflection_worker 角色。
        ctx = UserCtx(
            tenant_id=traj.tenant_id,
            user_id=traj.user_id,
            roles=[_REFLECTION_ROLE],
            data_scope={},
            permissions=[],
        )
        summary = traj.summary_seed or (
            f"任务『{traj.task_signature}』{traj.final_status};工具:{'→'.join(traj.tool_sequence)}"
        )
        episodic = await self._memory.save_episodic(ctx, summary, importance=0.6)

        score = score_trajectory(traj)
        experience_id, stored = "", False
        if score >= EXPERIENCE_THRESHOLD:  # 唯一入库门槛
            entry = ExperienceEntry(
                task_signature=traj.task_signature,
                applicability=f"终态={traj.final_status}",
                effective_path="→".join(traj.tool_sequence),
                pitfalls=f"重试={traj.retry_count}",
                cost=f"工具数={len(traj.tool_sequence)}",
                tags=[traj.task_signature],
            )
            result = await self._memory.record_experience(ctx, entry)
            experience_id, stored = result.memory_id, result.stored

        self._improvement_dir.mkdir(parents=True, exist_ok=True)
        improvement_path = self._improvement_dir / f"{uuid.uuid4().hex}.json"
        improvement_path.write_text(
            json.dumps(
                {
                    "trace_id": traj.trace_id,
                    "task_signature": traj.task_signature,
                    "score": score,
                    "suggestion": "复盘检索 miss / 语义层口径 / 文档 / SOP 缺口",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _log.info(
            "reflection",
            trace_id=traj.trace_id,
            tenant_id=traj.tenant_id,
            user_id=traj.user_id,
            score=score,
            experience_stored=stored,
        )
        return ReflectionOutcome(
            episodic_id=episodic.memory_id,
            experience_id=experience_id,
            experience_stored=stored,
            score=score,
            improvement_path=str(improvement_path),
        )
