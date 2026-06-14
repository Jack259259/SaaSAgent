"""运行实例持久化。InMemoryRunStore(本阶段);postgres 表 TODO(接口化以便替换)。"""

from __future__ import annotations

from typing import Protocol

from .models import RunState


class RunStore(Protocol):
    def save(self, state: RunState) -> None: ...

    def get(self, run_id: str) -> RunState | None: ...


class InMemoryRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}

    def save(self, state: RunState) -> None:
        self._runs[state.run_id] = state.model_copy(deep=True)  # 落盘语义:存快照,防别名

    def get(self, run_id: str) -> RunState | None:
        state = self._runs.get(run_id)
        return state.model_copy(deep=True) if state is not None else None
