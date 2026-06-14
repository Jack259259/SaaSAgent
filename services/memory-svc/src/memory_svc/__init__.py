"""memory-svc:分层记忆(画像/情景/经验)存取 + 脱敏 + 重要性门槛 + 租户隔离(方案 §7)。

对外能力经 save_memory / search_memory 契约;经验仅 reflection-worker 可录(9b)。
"""

from __future__ import annotations

from .models import (
    ExperienceEntry,
    MemoryHit,
    MemoryKind,
    OpeningContext,
    SaveResult,
    StoredMemory,
)
from .redaction import BasicRedactor, Redactor
from .service import MemoryService
from .store import InMemoryMemoryStore, MemoryStore

__version__ = "0.1.0"

__all__ = [
    "BasicRedactor",
    "ExperienceEntry",
    "InMemoryMemoryStore",
    "MemoryHit",
    "MemoryKind",
    "MemoryService",
    "MemoryStore",
    "OpeningContext",
    "Redactor",
    "SaveResult",
    "StoredMemory",
    "__version__",
]
