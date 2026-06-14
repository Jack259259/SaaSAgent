"""写入门槛(§7.2):重要性评分阈值 + 去重,避免垃圾记忆。先简单实现。"""

from __future__ import annotations

_THRESHOLD = 0.3


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def should_store(importance: float, content: str, existing_contents: set[str]) -> bool:
    """重要性达阈值且非重复(规范化后)才入库。"""
    if importance < _THRESHOLD:
        return False
    return _normalize(content) not in existing_contents


def normalize(text: str) -> str:
    return _normalize(text)
