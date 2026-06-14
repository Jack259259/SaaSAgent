"""reflection-worker:事后反思(方案 §8)。消费任务终态 → 情景记忆 + 经验条目(评分门槛)+ 改进工单。

经验入库唯一路径(reflection_worker 角色 + 评分过阈,呼应 9a)。本阶段队列轮询,真消息队列 TODO。
"""

from __future__ import annotations

from .models import ReflectionOutcome, TrajectoryRecord
from .queue import ReflectionQueue, SqliteReflectionQueue
from .scoring import EXPERIENCE_THRESHOLD, score_trajectory
from .worker import ReflectionWorker

__version__ = "0.1.0"

__all__ = [
    "EXPERIENCE_THRESHOLD",
    "ReflectionOutcome",
    "ReflectionQueue",
    "ReflectionWorker",
    "SqliteReflectionQueue",
    "TrajectoryRecord",
    "__version__",
    "score_trajectory",
]
