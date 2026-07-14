"""真实 wrenai 集成回归(装了可选 extra "wren" 才跑,否则整模块跳过)。

锚定风险 R5:真实 dry_plan 输出形态(同名 CTE + __source 内层)必须能过校验层
白名单并注入 RLS —— wrenai 升级后此测试是第一道回归。
运行:uv sync --all-packages --extra wren && make test SVC=data-svc
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("wren", reason="需要可选依赖 wrenai(uv sync --all-packages --extra wren)")

from data_svc import SemanticLayer, SqlValidator
from data_svc.wren_local import _WrenCorePlanner

_PROJECT_DIR = Path("assets/semantic-layer/wren")
_TABLES_YAML = Path("assets/semantic-layer/tables.yaml")


@pytest.fixture(scope="module")
def planner() -> _WrenCorePlanner:
    return _WrenCorePlanner(_PROJECT_DIR)


@pytest.fixture()
def validator() -> SqlValidator:
    return SqlValidator(SemanticLayer.load(_TABLES_YAML))


@pytest.mark.parametrize(
    "sql,tables",
    [
        ("SELECT plan_id, plan_amount FROM fund_plan WHERE period = '2026Q1'", {"fund_plan"}),
        (
            "SELECT p.plan_id, COUNT(f.flow_id) AS n FROM fund_plan p "
            "LEFT JOIN exec_flow f ON f.plan_id = p.plan_id GROUP BY p.plan_id",
            {"fund_plan", "exec_flow"},
        ),
        (
            "SELECT plan_id FROM fund_plan WHERE plan_id IN "
            "(SELECT plan_id FROM exec_flow WHERE status = 'FAILED')",
            {"fund_plan", "exec_flow"},
        ),
    ],
)
def test_dry_plan_output_passes_validator_with_rls(
    planner: _WrenCorePlanner, validator: SqlValidator, sql: str, tables: set[str]
) -> None:
    planned = planner.plan(sql)
    out = validator.validate(planned, tenant_id="t1")
    assert {a.table for a in out.lineage.rls_applied} == tables  # 每张涉及表都注入了租户谓词
    assert out.sql.count("tenant_id = 't1'") >= len(tables)


def test_dry_plan_rejects_unknown_table_strict(planner: _WrenCorePlanner) -> None:
    with pytest.raises(Exception, match="secret_table"):
        planner.plan("SELECT * FROM secret_table")


def test_dry_plan_rejects_data_reading_function(planner: _WrenCorePlanner) -> None:
    with pytest.raises(Exception, match=r"(?i)read"):
        planner.plan("SELECT * FROM read_csv('x.csv')")


def test_dry_plan_raises_on_syntax_error_with_message(planner: _WrenCorePlanner) -> None:
    with pytest.raises(Exception, match=r"(?i)invalid|unexpected"):
        planner.plan("SELEC plan_id FROM fund_plan")
