"""SQL 校验层(红线 6):只读断言、白名单、RLS 注入(含子查询/CTE)、LIMIT、解析失败。"""

from __future__ import annotations

import pytest

from data_svc import SqlValidator
from data_svc.errors import ValidationError


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO fund_plan VALUES ('x','t1','o','p',1,1,'CNY','v')",
        "UPDATE fund_plan SET plan_amount = 0",
        "DELETE FROM fund_plan",
        "DROP TABLE fund_plan",
        "ALTER TABLE fund_plan ADD COLUMN x INT",
        "SELECT plan_id FROM fund_plan; DROP TABLE fund_plan",
        "WITH t AS (DELETE FROM fund_plan RETURNING plan_id) SELECT plan_id FROM t",
    ],
)
def test_dml_ddl_rejected(validator: SqlValidator, sql: str) -> None:
    with pytest.raises(ValidationError):
        validator.validate(sql, tenant_id="t1")


def test_table_not_in_allowlist_rejected(validator: SqlValidator) -> None:
    with pytest.raises(ValidationError, match="白名单"):
        validator.validate("SELECT * FROM pg_catalog.pg_user", tenant_id="t1")


def test_parse_failure_rejected(validator: SqlValidator) -> None:
    with pytest.raises(ValidationError):
        validator.validate("SELECT * FROM (SELECT", tenant_id="t1")


def test_rls_injected_simple(validator: SqlValidator) -> None:
    out = validator.validate("SELECT plan_id FROM fund_plan", tenant_id="t1")
    assert "tenant_id = 't1'" in out.sql
    assert [a.table for a in out.lineage.rls_applied] == ["fund_plan"]


def test_rls_value_is_caller_tenant(validator: SqlValidator) -> None:
    out = validator.validate("SELECT plan_id FROM fund_plan", tenant_id="t2")
    assert "tenant_id = 't2'" in out.sql
    assert "tenant_id = 't1'" not in out.sql


def test_rls_injected_in_nested_subquery(validator: SqlValidator) -> None:
    # 外层 plan_subject + 内层子查询 fund_plan,两个作用域都应被注入(嵌套覆盖)。
    sql = (
        "SELECT s.subject_id FROM plan_subject s WHERE s.plan_id IN (SELECT plan_id FROM fund_plan)"
    )
    out = validator.validate(sql, tenant_id="t1")
    assert out.sql.count("tenant_id = 't1'") == 2
    assert set(a.table for a in out.lineage.rls_applied) == {"plan_subject", "fund_plan"}


def test_cte_definition_injected_reference_not_table(validator: SqlValidator) -> None:
    # CTE 定义内的 fund_plan 被注入;外层对 CTE 名 p 的引用不当基表(不报白名单错)。
    sql = "WITH p AS (SELECT plan_id, tenant_id FROM fund_plan) SELECT plan_id FROM p"
    out = validator.validate(sql, tenant_id="t1")
    assert "tenant_id = 't1'" in out.sql
    assert [a.table for a in out.lineage.rls_applied] == ["fund_plan"]


def test_limit_added_when_missing(validator: SqlValidator) -> None:
    out = validator.validate("SELECT plan_id FROM fund_plan", tenant_id="t1")
    assert "LIMIT 1000" in out.sql.upper()
    assert out.lineage.limit == 1000


def test_limit_capped_when_over(validator: SqlValidator) -> None:
    out = validator.validate("SELECT plan_id FROM fund_plan LIMIT 5000", tenant_id="t1")
    assert out.lineage.limit == 1000
    assert "5000" not in out.sql


def test_limit_kept_when_under(validator: SqlValidator) -> None:
    out = validator.validate("SELECT plan_id FROM fund_plan LIMIT 10", tenant_id="t1")
    assert out.lineage.limit == 10
