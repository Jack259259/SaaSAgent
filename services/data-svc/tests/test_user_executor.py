"""run_sql 接入函数(DuckDB 占位)+ DataFrameFunctionExecutor 适配器 + 问句→数据全链路。"""

from __future__ import annotations

import json
from pathlib import Path

from contracts import UserCtx
from data_svc import (
    DataFrameFunctionExecutor,
    DataService,
    SemanticLayer,
    SqlValidator,
    WrenLocalEngine,
    run_sql,
)
from llm import MockProvider, ScriptedTurn


def _ctx(tenant: str = "t1") -> UserCtx:
    return UserCtx(tenant_id=tenant, user_id="u", roles=["analyst"], data_scope={})


def _validator() -> SqlValidator:
    return SqlValidator(SemanticLayer.load(Path("assets/semantic-layer/tables.yaml")))


class _PassthroughPlanner:
    def plan(self, sql: str) -> str:
        return sql


def test_run_sql_returns_dataframe() -> None:
    df = run_sql("SELECT plan_id FROM fund_plan ORDER BY plan_id")
    assert list(df["plan_id"]) == ["P1", "P2", "P3", "P9"]


def test_explain_ok_and_fail() -> None:
    executor = DataFrameFunctionExecutor(run_sql)
    assert executor.explain("SELECT plan_id FROM fund_plan").ok
    bad = executor.explain("SELECT no_such_col FROM fund_plan")
    assert not bad.ok
    assert bad.error  # 首行错误信息,供外层自纠回流


def test_execute_converts_dataframe_to_json_safe_rows() -> None:
    executor = DataFrameFunctionExecutor(run_sql)
    res = executor.execute(
        "SELECT flow_id, exec_date, amount FROM exec_flow WHERE flow_id = 'F1'",
        timeout_ms=1000,
    )
    assert res.columns == ["flow_id", "exec_date", "amount"]
    assert res.elapsed_ms >= 0
    row = res.rows[0]
    assert row[0] == "F1"
    # DATE 经 pandas 提升为 Timestamp,归一为 ISO 字符串(日期部分在前)。
    assert isinstance(row[1], str) and row[1].startswith("2026-01-10")
    json.dumps(res.rows)  # 整体必须 JSON 可序列化(落工作区句柄的前提,红线 8)


def test_rls_injected_sql_executes_tenant_isolated() -> None:
    validated = _validator().validate("SELECT plan_id FROM fund_plan", tenant_id="t1")
    res = DataFrameFunctionExecutor(run_sql).execute(validated.sql, timeout_ms=1000)
    assert {r[0] for r in res.rows} == {"P1", "P2", "P3"}  # t2 的 P9 不可见

    validated_t2 = _validator().validate("SELECT plan_id FROM fund_plan", tenant_id="t2")
    res_t2 = DataFrameFunctionExecutor(run_sql).execute(validated_t2.sql, timeout_ms=1000)
    assert {r[0] for r in res_t2.rows} == {"P9"}


async def test_full_chain_question_to_dataframe_result() -> None:
    """问句 → WrenLocalEngine(Mock) → 校验层(RLS) → run_sql(占位 DuckDB) → QueryResult。"""
    engine = WrenLocalEngine(
        provider=MockProvider(
            [
                ScriptedTurn(
                    text=(
                        "```sql\nSELECT org_id, SUM(plan_amount) AS total_plan_amount "
                        "FROM fund_plan WHERE period = '2026Q1' "
                        "GROUP BY org_id ORDER BY org_id\n```"
                    )
                )
            ]
        ),
        planner=_PassthroughPlanner(),
    )
    service = DataService(
        engine=engine, validator=_validator(), executor=DataFrameFunctionExecutor(run_sql)
    )
    result = await service.query("2026年一季度各组织的计划金额合计", _ctx("t1"))
    assert "tenant_id = 't1'" in result.sql
    assert result.lineage.engine == "wren_local"
    assert result.columns == ["org_id", "total_plan_amount"]
    assert [[row[0], float(row[1])] for row in result.rows] == [["O1", 100.0], ["O2", 200.0]]
    assert result.row_count == 2
