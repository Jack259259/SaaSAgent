"""红线 5/6:SQL 校验层安全负例(中心红线索引 + 边界补缺)。

穷举用例(DML/DDL/堆叠/CTE-DELETE/白名单/解析失败/LIMIT 上限/嵌套子查询·CTE 的 RLS 注入)
为**单一事实源**,见 `services/data-svc/tests/test_validator.py` 与 `test_executor.py`。
本文件只做两件事:
1. 红线索引——中心套件保留一条"写/DDL 必拒 + 越白名单必拒"的哨兵,确保 RL5/6 在 tests/security 可见;
2. 补此前未覆盖的边界(S4):集合运算各臂注入、无租户列表的设计行为、用户自带 tenant 谓词不能放大范围。

铁律:失败即拒(ValidationError);绝无"测试态放行"。本文件只新增断言,不改被测代码。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data_svc import SemanticLayer, SqlValidator
from data_svc.errors import ValidationError
from data_svc.semantic_layer import TableSpec

_TABLES_YAML = Path(__file__).parents[2] / "assets" / "semantic-layer" / "tables.yaml"


@pytest.fixture
def validator() -> SqlValidator:
    return SqlValidator(SemanticLayer.load(_TABLES_YAML), max_rows=1000)


# ---- 红线索引:核心只读断言(穷举见 data-svc/test_validator.py)---------------- #
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE fund_plan SET plan_amount = 0",
        "DELETE FROM fund_plan",
        "DROP TABLE fund_plan",
        "SELECT plan_id FROM fund_plan; DROP TABLE fund_plan",  # 堆叠写
    ],
)
def test_write_or_ddl_rejected(validator: SqlValidator, sql: str) -> None:
    with pytest.raises(ValidationError):
        validator.validate(sql, tenant_id="t1")


def test_table_not_in_allowlist_rejected(validator: SqlValidator) -> None:
    with pytest.raises(ValidationError):
        validator.validate("SELECT * FROM pg_catalog.pg_user", tenant_id="t1")


# ---- 补缺 S4:边界负例 ------------------------------------------------------- #
def test_union_injects_rls_in_every_arm(validator: SqlValidator) -> None:
    # 集合运算每个 SELECT 作用域都须注入租户谓词,任一臂漏注 = 跨租户泄漏(红线 6)。
    out = validator.validate(
        "SELECT plan_id FROM fund_plan UNION SELECT subject_id FROM plan_subject",
        tenant_id="t1",
    )
    assert out.sql.count("tenant_id = 't1'") == 2  # 两臂都注入
    assert {a.table for a in out.lineage.rls_applied} == {"fund_plan", "plan_subject"}


def test_user_supplied_tenant_predicate_cannot_widen(validator: SqlValidator) -> None:
    # 调用者自带 WHERE tenant_id='t2',注入谓词仍以 AND 叠加 't1' → 无法越租户取数。
    out = validator.validate("SELECT plan_id FROM fund_plan WHERE tenant_id = 't2'", tenant_id="t1")
    assert "tenant_id = 't1'" in out.sql
    assert any(a.table == "fund_plan" for a in out.lineage.rls_applied)


def test_allowed_table_without_tenant_column_is_not_injected() -> None:
    # 参考维表(无 tenant 列)按设计不注入 RLS,但仍须在白名单内;锁定该行为以防误判为漏注。
    sem = SemanticLayer(
        tables={
            "ref_currency": TableSpec(
                name="ref_currency", columns=("code", "name"), tenant_column=None
            )
        }
    )
    validator = SqlValidator(sem, max_rows=1000)
    out = validator.validate("SELECT code FROM ref_currency", tenant_id="t1")
    assert out.lineage.rls_applied == []  # 无租户列 → 不注入
    assert "tenant_id" not in out.sql


def test_unlisted_table_rejected_even_when_layer_has_only_nontenant_table() -> None:
    # 即便语义层只配了无租户列的参考表,未登记的业务表仍因白名单拒(白名单与 RLS 是两道闸)。
    sem = SemanticLayer(
        tables={
            "ref_currency": TableSpec(name="ref_currency", columns=("code",), tenant_column=None)
        }
    )
    validator = SqlValidator(sem, max_rows=1000)
    with pytest.raises(ValidationError):
        validator.validate("SELECT * FROM fund_plan", tenant_id="t1")
