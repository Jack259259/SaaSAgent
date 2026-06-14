"""只读执行器:EXPLAIN 干跑 + 执行。

DuckDBExecutor:测试用(内存库 + fixture 表)。
PostgresExecutor:生产用,读 DB_DSN_READONLY + 只读事务 + statement_timeout;
未配置 / 未装驱动 → NOT_CONFIGURED。
校验在上游 SqlValidator 已完成;执行器只跑已校验、已注入 RLS 的 SELECT,不旁路任何校验。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import duckdb

from .errors import NotConfiguredError


@dataclass
class ExplainResult:
    ok: bool
    error: str | None = None


@dataclass
class ExecResult:
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    elapsed_ms: float = 0.0


class ReadOnlyExecutor(Protocol):
    def explain(self, sql: str) -> ExplainResult: ...

    def execute(self, sql: str, *, timeout_ms: int) -> ExecResult: ...


class DuckDBExecutor:
    """DuckDB 执行器(测试替身)。statement_timeout 由生产 Postgres 路径负责,此处从略。"""

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._con = connection

    def explain(self, sql: str) -> ExplainResult:
        try:
            self._con.execute(f"EXPLAIN {sql}")
        except duckdb.Error as exc:
            return ExplainResult(ok=False, error=str(exc).splitlines()[0])
        return ExplainResult(ok=True)

    def execute(self, sql: str, *, timeout_ms: int) -> ExecResult:
        start = time.perf_counter()
        cur = self._con.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = [list(r) for r in cur.fetchall()]
        return ExecResult(
            columns=columns, rows=rows, elapsed_ms=(time.perf_counter() - start) * 1000
        )


class PostgresExecutor:
    """只读账号执行器(生产)。本阶段不连接:无 DSN 或无 psycopg → NOT_CONFIGURED。"""

    def __init__(self, *, dsn: str | None = None, statement_timeout_ms: int = 30000) -> None:
        self._dsn = dsn if dsn is not None else os.environ.get("DB_DSN_READONLY")
        self._stmt_timeout = statement_timeout_ms

    def _connect(self) -> Any:
        if not self._dsn:
            raise NotConfiguredError("DB_DSN_READONLY 未配置")
        try:
            import psycopg
        except ImportError as exc:  # 生产依赖,本阶段未安装
            raise NotConfiguredError("psycopg 未安装(生产依赖)") from exc
        conn = psycopg.connect(self._dsn, autocommit=False)
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET statement_timeout = %s", (self._stmt_timeout,))
        return conn

    def explain(self, sql: str) -> ExplainResult:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f"EXPLAIN {sql}")
            return ExplainResult(ok=True)
        finally:
            conn.close()

    def execute(self, sql: str, *, timeout_ms: int) -> ExecResult:
        start = time.perf_counter()
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {int(timeout_ms)}")
                cur.execute(sql)
                columns = [d.name for d in cur.description] if cur.description else []
                rows = [list(r) for r in cur.fetchall()]
            return ExecResult(
                columns=columns, rows=rows, elapsed_ms=(time.perf_counter() - start) * 1000
            )
        finally:
            conn.close()
