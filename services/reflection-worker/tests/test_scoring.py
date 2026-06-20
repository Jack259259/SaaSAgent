"""经验评分启发式:采纳+低重试高分;拒绝+多重试低分。"""

from __future__ import annotations

from typing import Any

import pytest

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


# ---- 边界与异常补强(W2):各因子分支 + 门槛边界 + 上下界 clamp ----------------- #
def test_none_feedback_completed_sits_exactly_on_threshold() -> None:
    # 中性反馈 + 完成 + 零重试 = 0.6,恰为门槛;锁定边界值,便于将来调阈时回归。
    score = score_trajectory(_traj(user_feedback="none", retry_count=0, final_status="completed"))
    assert score == pytest.approx(EXPERIENCE_THRESHOLD)


def test_unknown_feedback_treated_as_neutral() -> None:
    # 未知反馈标签按 0 权重(default 分支),等同 none,不抬不压。
    score = score_trajectory(_traj(user_feedback="???", retry_count=0, final_status="completed"))
    assert score == pytest.approx(0.6)


def test_retry_penalty_can_pull_positive_feedback_below_threshold() -> None:
    # 即便点赞 + 完成,过多重试(噪声轨迹)仍应压到门槛下,避免污染经验库。
    score = score_trajectory(
        _traj(user_feedback="thumbs_up", retry_count=4, final_status="completed")
    )
    assert score < EXPERIENCE_THRESHOLD  # 0.5 + 0.3 + 0.1 - 0.4 = 0.5


def test_score_clamped_to_zero_floor() -> None:
    score = score_trajectory(_traj(user_feedback="rejected", retry_count=3, final_status="failed"))
    assert score == 0.0  # 0.5 - 0.4 - 0.2 - 0.3 = -0.4 → 下界 clamp 到 0


def test_score_clamped_to_one_ceiling() -> None:
    score = score_trajectory(
        _traj(user_feedback="adopted", retry_count=0, final_status="completed")
    )
    assert score == pytest.approx(1.0)  # 0.5 + 0.4 + 0.1 = 1.0,上界不被突破
