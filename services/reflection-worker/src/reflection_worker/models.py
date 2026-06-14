"""事后反思模型(方案 §8.2)。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_FORBID = ConfigDict(extra="forbid")


class TrajectoryRecord(BaseModel):
    """任务终态轨迹(反思输入):完整工具序列 + 终态 + 用户反馈。"""

    model_config = _FORBID

    trace_id: str
    tenant_id: str
    user_id: str
    task_signature: str
    tool_sequence: list[str] = Field(default_factory=list)
    retry_count: int = 0
    user_feedback: str = "none"  # adopted | thumbs_up | none | thumbs_down | rejected
    final_status: str = "completed"
    summary_seed: str = ""


class ReflectionOutcome(BaseModel):
    """一次反思的产出(三件套留痕)。"""

    model_config = _FORBID

    episodic_id: str
    experience_id: str = ""
    experience_stored: bool = False
    score: float = 0.0
    improvement_path: str = ""
