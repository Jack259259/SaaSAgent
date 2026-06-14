"""分层记忆模型(方案 §7 / §8.2)。

StoredMemory 为存储统一单元(三类共用,带 embedding 与脱敏后 content);
ExperienceEntry 为经验录入的结构化输入(§8.2),服务侧序列化为 StoredMemory。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

_FORBID = ConfigDict(extra="forbid")


class MemoryKind(StrEnum):
    profile = "profile"
    episodic = "episodic"
    experience = "experience"


class StoredMemory(BaseModel):
    """存储统一单元。content 已脱敏;search_text 供向量检索(亦脱敏)。"""

    model_config = _FORBID

    memory_id: str
    tenant_id: str
    user_id: str
    kind: MemoryKind
    content: str
    search_text: str
    scope: str = ""  # profile 类:profile|preference|glossary
    importance: float = 0.5
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] = Field(default_factory=list)
    created_at: str = ""


class ExperienceEntry(BaseModel):
    """经验条目(§8.2)。仅 reflection-worker 录入(本阶段不建反思管道)。"""

    model_config = _FORBID

    task_signature: str
    applicability: str
    effective_path: str
    pitfalls: str = ""
    cost: str = ""
    tags: list[str] = Field(default_factory=list)


class MemoryHit(BaseModel):
    model_config = _FORBID

    kind: MemoryKind
    content: str
    score: float


class SaveResult(BaseModel):
    model_config = _FORBID

    memory_id: str
    stored: bool


class OpeningContext(BaseModel):
    """开场注入素材(画像全量 + 情景/经验 TopK)。"""

    model_config = _FORBID

    profile: list[str] = Field(default_factory=list)
    memories: list[MemoryHit] = Field(default_factory=list)
    experiences: list[MemoryHit] = Field(default_factory=list)
