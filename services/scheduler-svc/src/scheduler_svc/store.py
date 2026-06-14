"""定时任务表(SQLite;接口化 ScheduleStore,postgres TODO)。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from .models import ScheduledTask

_COLUMNS = (
    "schedule_id, tenant_id, user_id, cron, action, max_runs, max_cost, "
    "runs_used, cost_used, consecutive_failures, confirmed, active, next_run_at"
)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS schedules (
    schedule_id TEXT PRIMARY KEY, tenant_id TEXT, user_id TEXT, cron TEXT, action TEXT,
    max_runs INTEGER, max_cost REAL, runs_used INTEGER, cost_used REAL,
    consecutive_failures INTEGER, confirmed INTEGER, active INTEGER, next_run_at REAL
);
CREATE INDEX IF NOT EXISTS idx_sched_owner ON schedules(tenant_id, user_id);
"""


def _to_task(row: sqlite3.Row) -> ScheduledTask:
    data = dict(row)
    data["confirmed"] = bool(data["confirmed"])
    data["active"] = bool(data["active"])
    return ScheduledTask(**data)


class ScheduleStore(Protocol):
    def add(self, task: ScheduledTask) -> None: ...

    def update(self, task: ScheduledTask) -> None: ...

    def get(self, schedule_id: str) -> ScheduledTask | None: ...

    def list_by_user(self, tenant_id: str, user_id: str) -> list[ScheduledTask]: ...

    def due(self, now: float) -> list[ScheduledTask]: ...


class SqliteScheduleStore:
    def __init__(self, db_path: Path | str = ":memory:") -> None:
        if isinstance(db_path, Path) and str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def _values(self, task: ScheduledTask) -> tuple[object, ...]:
        return (
            task.schedule_id,
            task.tenant_id,
            task.user_id,
            task.cron,
            task.action,
            task.max_runs,
            task.max_cost,
            task.runs_used,
            task.cost_used,
            task.consecutive_failures,
            int(task.confirmed),
            int(task.active),
            task.next_run_at,
        )

    def add(self, task: ScheduledTask) -> None:
        placeholders = ",".join(["?"] * 13)
        self._conn.execute(
            f"INSERT INTO schedules ({_COLUMNS}) VALUES ({placeholders})", self._values(task)
        )
        self._conn.commit()

    def update(self, task: ScheduledTask) -> None:
        assignments = ",".join(f"{c.strip()} = ?" for c in _COLUMNS.split(","))
        self._conn.execute(
            f"UPDATE schedules SET {assignments} WHERE schedule_id = ?",
            (*self._values(task), task.schedule_id),
        )
        self._conn.commit()

    def get(self, schedule_id: str) -> ScheduledTask | None:
        row = self._conn.execute(
            f"SELECT {_COLUMNS} FROM schedules WHERE schedule_id = ?", (schedule_id,)
        ).fetchone()
        return _to_task(row) if row else None

    def list_by_user(self, tenant_id: str, user_id: str) -> list[ScheduledTask]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM schedules "
            "WHERE tenant_id = ? AND user_id = ? ORDER BY schedule_id",
            (tenant_id, user_id),
        ).fetchall()
        return [_to_task(r) for r in rows]

    def due(self, now: float) -> list[ScheduledTask]:
        rows = self._conn.execute(
            f"SELECT {_COLUMNS} FROM schedules "
            "WHERE active = 1 AND confirmed = 1 AND next_run_at <= ? ORDER BY schedule_id",
            (now,),
        ).fetchall()
        return [_to_task(r) for r in rows]
