"""反思队列(SQLite 队列表轮询;接口化 ReflectionQueue,真消息队列 TODO)。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from .models import TrajectoryRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reflection_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT, processed INTEGER DEFAULT 0
);
"""


class ReflectionQueue(Protocol):
    def enqueue(self, trajectory: TrajectoryRecord) -> None: ...

    def dequeue(self) -> TrajectoryRecord | None: ...


class SqliteReflectionQueue:
    def __init__(self, db_path: Path | str = ":memory:") -> None:
        if isinstance(db_path, Path) and str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def enqueue(self, trajectory: TrajectoryRecord) -> None:
        self._conn.execute(
            "INSERT INTO reflection_queue(payload, processed) VALUES (?, 0)",
            (trajectory.model_dump_json(),),
        )
        self._conn.commit()

    def dequeue(self) -> TrajectoryRecord | None:
        row = self._conn.execute(
            "SELECT id, payload FROM reflection_queue WHERE processed = 0 ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        self._conn.execute("UPDATE reflection_queue SET processed = 1 WHERE id = ?", (row["id"],))
        self._conn.commit()
        return TrajectoryRecord.model_validate_json(row["payload"])
