"""data-svc 运行时模型(方案 §5.2)。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_FORBID = ConfigDict(extra="forbid")


class Clarification(BaseModel):
    """字段/口径歧义时的结构化澄清项(§5.2:不猜,返回选项)。"""

    model_config = _FORBID

    field: str
    question: str
    options: list[str] = Field(default_factory=list)


class Nl2SqlResult(BaseModel):
    """NL2SQLEngine 产出:要么给 SQL,要么给澄清项(二选一)。"""

    model_config = _FORBID

    sql: str | None = None
    clarifications: list[Clarification] = Field(default_factory=list)


class RlsApplied(BaseModel):
    """一处已注入的租户谓词(lineage 留痕,便于核对红线 6)。"""

    model_config = _FORBID

    table: str
    predicate: str


class Lineage(BaseModel):
    """取数血缘:涉及表、注入的 RLS 谓词、LIMIT、生成引擎。"""

    model_config = _FORBID

    tables: list[str] = Field(default_factory=list)
    rls_applied: list[RlsApplied] = Field(default_factory=list)
    limit: int | None = None
    engine: str = "unknown"


class ValidatedQuery(BaseModel):
    """校验层输出:重写后的最终 SQL + 血缘。"""

    model_config = _FORBID

    sql: str
    lineage: Lineage


class QueryResult(BaseModel):
    """取数最终结果。rows 由 handler 落工作区句柄,不进上下文(红线 8)。"""

    model_config = _FORBID

    summary: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    sql: str
    lineage: Lineage
    row_count: int
    elapsed_ms: float
