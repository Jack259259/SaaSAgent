"""SQLite 符号库:定义/引用/调用边 + 文件元数据(增量索引)。

查询:find_definition / find_references / find_callers;repo map 用度数统计。
读多写少;连接 check_same_thread=False 以配合工具并行(只读为主)。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import CallEdge, Definition, Reference

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY, language TEXT, mtime REAL, size INTEGER
);
CREATE TABLE IF NOT EXISTS defs (
    name TEXT, kind TEXT, language TEXT, file TEXT,
    start_line INTEGER, end_line INTEGER, snippet TEXT
);
CREATE TABLE IF NOT EXISTS refs (
    name TEXT, file TEXT, line INTEGER, snippet TEXT
);
CREATE TABLE IF NOT EXISTS calls (
    caller TEXT, callee TEXT, file TEXT, line INTEGER, snippet TEXT
);
CREATE INDEX IF NOT EXISTS idx_defs_name ON defs(name);
CREATE INDEX IF NOT EXISTS idx_defs_file ON defs(file);
CREATE INDEX IF NOT EXISTS idx_refs_name ON refs(name);
CREATE INDEX IF NOT EXISTS idx_refs_file ON refs(file);
CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls(callee);
CREATE INDEX IF NOT EXISTS idx_calls_caller ON calls(caller);
CREATE INDEX IF NOT EXISTS idx_calls_file ON calls(file);
"""


class SymbolStore:
    def __init__(self, db_path: Path) -> None:
        if db_path != Path(":memory:"):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    # ---- 增量写入 -------------------------------------------------------- #
    def file_meta(self, path: str) -> tuple[float, int] | None:
        row = self._conn.execute("SELECT mtime, size FROM files WHERE path = ?", (path,)).fetchone()
        return (row["mtime"], row["size"]) if row else None

    def indexed_files(self) -> set[str]:
        return {r["path"] for r in self._conn.execute("SELECT path FROM files")}

    def remove_file(self, path: str) -> None:
        for table in ("defs", "refs", "calls"):
            self._conn.execute(f"DELETE FROM {table} WHERE file = ?", (path,))
        self._conn.execute("DELETE FROM files WHERE path = ?", (path,))

    def replace_file(
        self,
        path: str,
        *,
        language: str,
        mtime: float,
        size: int,
        defs: list[Definition],
        refs: list[Reference],
        calls: list[CallEdge],
    ) -> None:
        self.remove_file(path)
        self._conn.execute(
            "INSERT INTO files(path, language, mtime, size) VALUES (?,?,?,?)",
            (path, language, mtime, size),
        )
        self._conn.executemany(
            "INSERT INTO defs VALUES (?,?,?,?,?,?,?)",
            [
                (d.name, d.kind, d.language, d.file, d.start_line, d.end_line, d.snippet)
                for d in defs
            ],
        )
        self._conn.executemany(
            "INSERT INTO refs VALUES (?,?,?,?)",
            [(r.name, r.file, r.line, r.snippet) for r in refs],
        )
        self._conn.executemany(
            "INSERT INTO calls VALUES (?,?,?,?,?)",
            [(c.caller, c.callee, c.file, c.line, c.snippet) for c in calls],
        )
        self._conn.commit()

    # ---- 查询 ------------------------------------------------------------ #
    def find_definition(self, name: str) -> list[Definition]:
        rows = self._conn.execute(
            "SELECT name, kind, language, file, start_line, end_line, snippet "
            "FROM defs WHERE name = ? ORDER BY file, start_line",
            (name,),
        ).fetchall()
        return [Definition(**dict(r)) for r in rows]

    def find_references(self, name: str, *, limit: int = 200) -> list[Reference]:
        rows = self._conn.execute(
            "SELECT name, file, line, snippet FROM refs WHERE name = ? ORDER BY file, line LIMIT ?",
            (name, limit),
        ).fetchall()
        return [Reference(**dict(r)) for r in rows]

    def find_callers(self, name: str, *, limit: int = 200) -> list[CallEdge]:
        rows = self._conn.execute(
            "SELECT caller, callee, file, line, snippet FROM calls WHERE callee = ? "
            "ORDER BY file, line LIMIT ?",
            (name, limit),
        ).fetchall()
        return [CallEdge(**dict(r)) for r in rows]

    def all_definitions(self) -> list[Definition]:
        rows = self._conn.execute(
            "SELECT name, kind, language, file, start_line, end_line, snippet FROM defs"
        ).fetchall()
        return [Definition(**dict(r)) for r in rows]

    def definition_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM defs").fetchone()
        return int(row["c"])

    def incoming_degree(self) -> dict[str, int]:
        """每个被调/被引名字的入度(callee 次数 + 引用次数)。"""
        degree: dict[str, int] = {}
        for table, col in (("calls", "callee"), ("refs", "name")):
            for r in self._conn.execute(
                f"SELECT {col} AS k, COUNT(*) AS c FROM {table} GROUP BY {col}"
            ):
                degree[r["k"]] = degree.get(r["k"], 0) + int(r["c"])
        return degree

    def outgoing_degree(self) -> dict[str, int]:
        """每个定义名的出度(其体内发起的调用次数)。"""
        return {
            r["caller"]: int(r["c"])
            for r in self._conn.execute("SELECT caller, COUNT(*) AS c FROM calls GROUP BY caller")
        }

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
