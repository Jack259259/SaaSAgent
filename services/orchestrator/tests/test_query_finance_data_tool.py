"""query_finance_data 工具集成(§5.2):AMBIGUOUS_FIELD → 编排器联动 ask_user → 二次取数成功。

引擎首问返回澄清项 → handler 透出 → 模型(脚本化)调 ask_user 暂停 → 恢复 → 明确问句取数成功;
断言最终 SQL 透出且含注入的 RLS 谓词(红线 6)。
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from contracts import UserCtx
from data_svc import (
    Clarification,
    DataService,
    DuckDBExecutor,
    SemanticLayer,
    SqlValidator,
    StubEngine,
)
from llm import MockProvider, ScriptedTurn, ToolUseBlock
from orchestrator import (
    AskUserEvent,
    DoneEvent,
    Orchestrator,
    Session,
    ToolCallEvent,
    ToolRegistry,
    ToolResultSummaryEvent,
)
from orchestrator.tools import make_query_finance_data_handler

_TABLES_YAML = Path(__file__).parents[3] / "assets" / "semantic-layer" / "tables.yaml"
_VAGUE = "执行率多少"
_CLEAR = "2026Q1 计划编号"


def _user_ctx() -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=["*"]
    )


def _data_service() -> DataService:
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE fund_plan (plan_id VARCHAR, tenant_id VARCHAR, org_id VARCHAR, "
        "period VARCHAR, plan_amount DOUBLE, exec_amount DOUBLE, currency VARCHAR, "
        "version VARCHAR);"
        "INSERT INTO fund_plan VALUES ('P1','t1','O1','2026Q1',100,60,'CNY','v1'),"
        "('P9','t2','O9','2026Q1',500,500,'CNY','v1');"
    )
    engine = StubEngine(
        {_CLEAR: "SELECT plan_id FROM fund_plan"},
        clarify={
            _VAGUE: [
                Clarification(
                    field="执行率口径", question="按哪种?", options=["含在途", "不含在途"]
                )
            ]
        },
    )
    validator = SqlValidator(SemanticLayer.load(_TABLES_YAML))
    return DataService(engine=engine, validator=validator, executor=DuckDBExecutor(con))


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register_from_contracts(
        {"query_finance_data": make_query_finance_data_handler(_data_service())}
    )
    return reg


def _session() -> Session:
    from llm import Message, Role, TextBlock

    s = Session(session_id="s-data", trace_id="t-data", user_ctx=_user_ctx())
    s.messages.append(Message(role=Role.user, content=[TextBlock("查执行率")]))
    return s


async def test_ambiguous_links_ask_user_then_succeeds() -> None:
    provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[
                    ToolUseBlock(id="d1", name="query_finance_data", input={"question": _VAGUE})
                ],
                stop_reason="tool_use",
            ),
            ScriptedTurn(
                tool_calls=[
                    ToolUseBlock(
                        id="a1",
                        name="ask_user",
                        input={
                            "questions": [
                                {"id": "q1", "prompt": "口径?", "options": ["含在途", "不含在途"]}
                            ]
                        },
                    )
                ],
                stop_reason="tool_use",
            ),
            ScriptedTurn(
                tool_calls=[
                    ToolUseBlock(id="d2", name="query_finance_data", input={"question": _CLEAR})
                ],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text="t1 仅有计划 P1", stop_reason="end_turn"),
        ]
    )
    orch = Orchestrator(provider=provider, registry=_registry())
    session = _session()

    seg1 = [e async for e in orch.advance(session)]
    # AMBIGUOUS → 模型联动 ask_user,暂停
    assert any(isinstance(e, AskUserEvent) for e in seg1)
    assert session.pending is not None and session.pending.kind == "ask_user"
    ambiguous = [e for e in seg1 if isinstance(e, ToolResultSummaryEvent)]
    assert "歧义" in ambiguous[0].summary
    assert not any(isinstance(e, DoneEvent) for e in seg1)

    seg2 = [e async for e in orch.resume(session, answers={"q1": "含在途"})]
    calls = [e for e in seg2 if isinstance(e, ToolCallEvent)]
    assert any(c.tool == "query_finance_data" for c in calls)
    successes = [e for e in seg2 if isinstance(e, ToolResultSummaryEvent)]
    assert any("取数完成" in e.summary for e in successes)
    # 最终 SQL 透出且含注入的 RLS 谓词(红线 6)
    success_ref = next(e.workspace_ref for e in successes if "取数完成" in e.summary)
    raw = session.workspace.get(success_ref).raw
    assert "tenant_id = 't1'" in raw["sql"]
    assert raw["table_ref"].startswith("ws://")
    done = [e for e in seg2 if isinstance(e, DoneEvent)]
    assert done[-1].stop_reason == "end_turn"
