"""经验评分启发式:采纳+低重试高分;拒绝+多重试低分。"""

from __future__ import annotations

from typing import Any

from reflection_worker import EXPERIENCE_THRESHOLD, TrajectoryRecord, score_trajectory


def _traj(**kw: Any) -> TrajectoryRecord:
    base: dict[str, Any] = {
        "trace_id": "t",
        "tenant_id": "t1",
        "user_id": "u1",
        "task_signature": "月度差异分析",
    }
    base.update(kw)
    return TrajectoryRecord(**base)


def test_adopted_low_retry_scores_high() -> None:
    score = score_trajectory(
        _traj(user_feedback="adopted", retry_count=0, final_status="completed")
    )
    assert score >= EXPERIENCE_THRESHOLD


def test_rejected_many_retries_scores_low() -> None:
    score = score_trajectory(_traj(user_feedback="rejected", retry_count=3, final_status="failed"))
    assert score < EXPERIENCE_THRESHOLD
