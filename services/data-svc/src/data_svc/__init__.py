"""data-svc 服务:WrenAI 代理 + SQL 校验层 + RLS 注入 + 只读执行(CLAUDE.md §3 / 方案 §5.2)。

红线 6 载体:只读账号(PostgresExecutor)+ 禁 DML/DDL(SqlValidator 只读断言)+ 强制租户谓词(RLS 注入)。
"""

from __future__ import annotations

from .engine import NL2SQLEngine, StubEngine, WrenAdapter
from .errors import (
    AmbiguousFieldError,
    DataSvcError,
    NotConfiguredError,
    QueryTimeoutError,
    ValidationError,
)
from .executor import (
    DuckDBExecutor,
    ExecResult,
    ExplainResult,
    PostgresExecutor,
    ReadOnlyExecutor,
)
from .models import (
    Clarification,
    Lineage,
    Nl2SqlResult,
    QueryResult,
    RlsApplied,
    ValidatedQuery,
)
from .semantic_layer import SemanticLayer, TableSpec
from .service import DataService
from .validator import SqlValidator

__version__ = "0.1.0"

__all__ = [
    "AmbiguousFieldError",
    "Clarification",
    "DataService",
    "DataSvcError",
    "DuckDBExecutor",
    "ExecResult",
    "ExplainResult",
    "Lineage",
    "NL2SQLEngine",
    "Nl2SqlResult",
    "NotConfiguredError",
    "PostgresExecutor",
    "QueryResult",
    "QueryTimeoutError",
    "ReadOnlyExecutor",
    "RlsApplied",
    "SemanticLayer",
    "SqlValidator",
    "StubEngine",
    "TableSpec",
    "ValidatedQuery",
    "ValidationError",
    "WrenAdapter",
    "__version__",
]
