"""经验条目评分(方案 §8.2)。启发式:用户反馈 + 重试次数 + 终态。

经验入库**必须**先过此评分门槛(红线/禁止项:绕过评分入库)。LLM-judge 为后续增强。
"""

from __future__ import annotations

from .models import TrajectoryRecord

EXPERIENCE_THRESHOLD = 0.6

_FEEDBACK_WEIGHT = {
    "adopted": 0.4,
    "thumbs_up": 0.3,
    "none": 0.0,
    "thumbs_down": -0.4,
    "rejected": -0.4,
}


def score_trajectory(trajectory: TrajectoryRecord) -> float:
    base = 0.5
    feedback = _FEEDBACK_WEIGHT.get(trajectory.user_feedback, 0.0)
    status_bonus = 0.1 if trajectory.final_status == "completed" else -0.2
    retry_penalty = 0.1 * trajectory.retry_count
    return max(0.0, min(1.0, base + feedback + status_bonus - retry_penalty))
