"""DataService:取数自纠小循环(方案 §5.2)。

engine 生成 → 校验层(失败=硬拒,不自纠,红线 6)→ EXPLAIN 干跑 → 失败带错回流自纠(≤2)
→ 只读执行 → QueryResult。tenant_id 由 user_ctx 自取(零信任,红线 3),交校验层注入 RLS。
"""

from __future__ import annotations

import asyncio

from contracts import UserCtx

from .engine import NL2SQLEngine
from .errors import AmbiguousFieldError, ValidationError
from .executor import ReadOnlyExecutor
from .models import QueryResult, ValidatedQuery
from .validator import SqlValidator

_MAX_CORRECTIONS = 2


class DataService:
    def __init__(
        self,
        *,
        engine: NL2SQLEngine,
        validator: SqlValidator,
        executor: ReadOnlyExecutor,
        max_corrections: int = _MAX_CORRECTIONS,
    ) -> None:
        self._engine = engine
        self._validator = validator
        self._executor = executor
        self._max_corrections = max_corrections

    async def query(
        self, question: str, user_ctx: UserCtx, *, timeout_ms: int = 30000
    ) -> QueryResult:
        validated = await self._generate_validated_runnable(question, user_ctx)
        exec_result = await asyncio.to_thread(
            self._executor.execute, validated.sql, timeout_ms=timeout_ms
        )
        summary = f"取数完成:{exec_result.elapsed_ms:.0f}ms,{len(exec_result.rows)} 行"
        return QueryResult(
            summary=summary,
            columns=exec_result.columns,
            rows=exec_result.rows,
            sql=validated.sql,
            lineage=validated.lineage,
            row_count=len(exec_result.rows),
            elapsed_ms=exec_result.elapsed_ms,
        )

    async def _generate_validated_runnable(
        self, question: str, user_ctx: UserCtx
    ) -> ValidatedQuery:
        prior_error: str | None = None
        attempts = 0
        while True:
            result = await self._engine.generate(question, user_ctx, prior_error=prior_error)
            if result.clarifications:
                raise AmbiguousFieldError("字段或口径有歧义", clarifications=result.clarifications)
            if result.sql is None:
                raise ValidationError("引擎未返回 SQL")
            # 校验层失败=硬拒(不自纠,不教模型绕闸,红线 6)。
            validated = self._validator.validate(result.sql, tenant_id=user_ctx.tenant_id)
            validated.lineage.engine = self._engine.name
            explain = await asyncio.to_thread(self._executor.explain, validated.sql)
            if explain.ok:
                return validated
            if attempts >= self._max_corrections:
                raise ValidationError("SQL 干跑失败且自纠超限")
            prior_error = explain.error
            attempts += 1
