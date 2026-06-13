"""共享工作区(内存实现)。大对象不进上下文,只回"摘要 + 句柄"(红线 8)。"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any


@dataclass
class WorkspaceItem:
    key: str
    type: str
    summary: str
    raw: Any


@dataclass
class WorkspacePage:
    chunk: str
    page: int
    total_pages: int
    eof: bool


class Workspace:
    """租户内会话级共享工作区(阶段 2 内存版;后续阶段可换持久化后端)。"""

    def __init__(self) -> None:
        self._items: dict[str, WorkspaceItem] = {}
        self._seq = 0

    def put(self, *, key: str, type: str, summary: str, raw: Any) -> str:
        self._seq += 1
        ref = f"ws://{key}/{self._seq}"
        self._items[ref] = WorkspaceItem(key=key, type=type, summary=summary, raw=raw)
        return ref

    def get(self, ref: str) -> WorkspaceItem:
        if ref not in self._items:
            raise KeyError(ref)
        return self._items[ref]

    def read(self, ref: str, *, page: int = 1, page_size: int = 2000) -> WorkspacePage:
        """按句柄分页读取(单次返回限额,§4.3)。"""
        if page < 1 or page_size < 1:
            raise ValueError("page 与 page_size 必须 ≥ 1")
        item = self.get(ref)
        text = item.raw if isinstance(item.raw, str) else json.dumps(item.raw, ensure_ascii=False)
        total_pages = max(1, math.ceil(len(text) / page_size))
        start = (page - 1) * page_size
        return WorkspacePage(
            chunk=text[start : start + page_size],
            page=page,
            total_pages=total_pages,
            eof=page >= total_pages,
        )

    def size(self) -> int:
        return len(self._items)
