"""只读执行器(DuckDB):EXPLAIN 干跑 + 执行;并验证注入的 RLS 谓词在执行层真实过滤行。"""

from __future__ import annotations

from data_svc import DuckDBExecutor, SqlValidator


def test_explain_ok(executor: DuckDBExecutor, validator: SqlValidator) -> None:
    out = validator.validate("SELECT plan_id FROM fund_plan", tenant_id="t1")
    assert executor.explain(out.sql).ok


def test_explain_fails_on_unknown_column(executor: DuckDBExecutor, validator: SqlValidator) -> None:
    # 通过校验(表合法、只读)但列不存在 → EXPLAIN 干跑失败(驱动自纠)。
    out = validator.validate("SELECT nonexistent_col FROM fund_plan", tenant_id="t1")
    result = executor.explain(out.sql)
    assert not result.ok
    assert result.error


def test_execute_returns_columns_and_rows(
    executor: DuckDBExecutor, validator: SqlValidator
) -> None:
    out = validator.validate("SELECT plan_id FROM fund_plan", tenant_id="t1")
    result = executor.execute(out.sql, timeout_ms=5000)
    assert result.columns == ["plan_id"]
    assert sorted(r[0] for r in result.rows) == ["P1", "P2"]  # RLS:仅 t1 行


def test_execute_rls_isolates_other_tenant(
    executor: DuckDBExecutor, validator: SqlValidator
) -> None:
    out = validator.validate("SELECT plan_id FROM fund_plan", tenant_id="t2")
    result = executor.execute(out.sql, timeout_ms=5000)
    assert [r[0] for r in result.rows] == ["P9"]  # 跨租户不可见(红线 6)
