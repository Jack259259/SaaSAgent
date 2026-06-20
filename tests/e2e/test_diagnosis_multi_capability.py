"""跨能力端到端(E1):一次"报表对不上"诊断串起 data-svc + rag-svc + code-svc 三个真实服务。

主编排器(MockProvider 剧本驱动)顺序调用:
1. query_finance_data —— 真实 DataService(DuckDB),取数经 SQL 校验层注入 RLS(红线 6);
2. search_knowledge   —— 真实 RagService(临时索引),检索前 ACL 过滤 + 引用(红线 5);
3. ask_codebase       —— 真实 CodeService(sample_repo)子 Agent,回传结构化证据(红线 12);
末轮综合作答。

剧本只描述"模型怎么走 + 期望性质",断言三能力证据齐备 + RLS 注入 + 正常完成,
不喂业务标准答案(§10 反模式)。子 Agent 用独立 MockProvider,避免与主循环剧本相互消费。
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from code_svc import CodeService, FileReader, PythonSearch, SymbolStore, index_repos
from contracts import UserCtx
from data_svc import DataService, DuckDBExecutor, SemanticLayer, SqlValidator, StubEngine
from llm import Message, MockProvider, Role, ScriptedTurn, TextBlock, ToolUseBlock
from orchestrator import (
    AnswerDeltaEvent,
    DoneEvent,
    Orchestrator,
    Session,
    ToolCallEvent,
    ToolRegistry,
    ToolResultSummaryEvent,
)
from orchestrator.tools import (
    make_ask_codebase_handler,
    make_query_finance_data_handler,
    make_search_knowledge_handler,
)
from rag_svc import RagService, acl
from rag_svc.ingest import ingest_dir

_ROOT = Path(__file__).parents[2]
_TABLES_YAML = _ROOT / "assets" / "semantic-layer" / "tables.yaml"
_SAMPLE_REPO = _ROOT / "services" / "code-svc" / "tests" / "fixtures" / "sample_repo"

_Q_DATA = "2026Q1 各计划执行率"
_Q_RAG = "执行率口径"
_Q_CODE = "执行率是如何计算的"


def _user_ctx(tenant: str = "t1") -> UserCtx:
    return UserCtx(
        tenant_id=tenant,
        user_id="u1",
        roles=["tenant_user", "internal_dev"],
        data_scope={},
        permissions=["*"],
    )


def _data_service() -> DataService:
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE fund_plan (plan_id VARCHAR, tenant_id VARCHAR, org_id VARCHAR, "
        "period VARCHAR, plan_amount DOUBLE, exec_amount DOUBLE, "
        "currency VARCHAR, version VARCHAR);"
        "INSERT INTO fund_plan VALUES "
        "('P1','t1','O1','2026Q1',100,60,'CNY','v1'),"
        "('P2','t1','O1','2026Q1',200,200,'CNY','v1'),"
        "('P9','t2','O9','2026Q1',500,500,'CNY','v1');"
    )
    engine = StubEngine({_Q_DATA: "SELECT plan_id, plan_amount, exec_amount FROM fund_plan"})
    validator = SqlValidator(SemanticLayer.load(_TABLES_YAML))
    return DataService(engine=engine, validator=validator, executor=DuckDBExecutor(con))


async def _rag_service(tmp_path: Path) -> RagService:
    src = tmp_path / "kb"
    src.mkdir()
    (src / "exec_rate.md").write_text(
        "---\nsource: 口径手册/执行率\nacl_tags: [tenant]\n---\n"
        "资金计划执行率口径:执行率 = 执行额 ÷ 计划额,口径含在途资金。\n",
        encoding="utf-8",
    )
    store = tmp_path / "store"
    await ingest_dir(kb=acl.KB_BUSINESS, src=src, store_dir=store, tenant="t1")
    return RagService.from_dir(store)


def _code_service(tmp_path: Path) -> CodeService:
    db = tmp_path / "symbols.db"
    index_repos(repos_root=_SAMPLE_REPO, db_path=db)
    return CodeService(
        repos_root=_SAMPLE_REPO,
        store=SymbolStore(db),
        search=PythonSearch(_SAMPLE_REPO, [_SAMPLE_REPO]),
        reader=FileReader(_SAMPLE_REPO),
    )


def _code_subagent_provider() -> MockProvider:
    answer = json.dumps(
        {
            "answer": "执行率由 calculator.execution_rate 计算,内部用 safe_div 防除零。",
            "evidences": [
                {
                    "file": "calculator.py",
                    "line_range": "5-7",
                    "snippet": "def execution_rate(plan)",
                }
            ],
            "confidence": 0.85,
            "followups": [],
        },
        ensure_ascii=False,
    )
    return MockProvider(
        [
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="c1", name="find_callers", input={"name": "safe_div"})],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text=answer, stop_reason="end_turn"),
        ]
    )


def _main_provider() -> MockProvider:
    return MockProvider(
        [
            ScriptedTurn(
                tool_calls=[
                    ToolUseBlock(id="d", name="query_finance_data", input={"question": _Q_DATA})
                ],
                stop_reason="tool_use",
            ),
            ScriptedTurn(
                tool_calls=[
                    ToolUseBlock(
                        id="k",
                        name="search_knowledge",
                        input={"question": _Q_RAG, "kb": acl.KB_BUSINESS},
                    )
                ],
                stop_reason="tool_use",
            ),
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="a", name="ask_codebase", input={"question": _Q_CODE})],
                stop_reason="tool_use",
            ),
            ScriptedTurn(
                text=(
                    "综合三方:取数显示 P1 执行率偏低,口径含在途,算法用 safe_div;差异源于在途口径。"
                ),
                stop_reason="end_turn",
            ),
        ]
    )


async def test_report_mismatch_diagnosis_spans_data_rag_code(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register_from_contracts(
        {
            "query_finance_data": make_query_finance_data_handler(_data_service()),
            "search_knowledge": make_search_knowledge_handler(await _rag_service(tmp_path)),
            "ask_codebase": make_ask_codebase_handler(
                _code_subagent_provider(), _code_service(tmp_path)
            ),
        }
    )
    orch = Orchestrator(provider=_main_provider(), registry=registry)
    session = Session(session_id="e2e-diag", trace_id="t-diag", user_ctx=_user_ctx())
    session.messages.append(
        Message(role=Role.user, content=[TextBlock("报表对不上,帮我诊断执行率差异")])
    )

    events = [e async for e in orch.advance(session)]

    # 三能力按序编排(跨能力诊断真链路)
    called = [e.tool for e in events if isinstance(e, ToolCallEvent)]
    assert called == ["query_finance_data", "search_knowledge", "ask_codebase"]

    results = {e.tool: e.workspace_ref for e in events if isinstance(e, ToolResultSummaryEvent)}

    # data:取数经校验层注入 RLS(红线 6 端到端)
    data_raw = session.workspace.get(results["query_finance_data"]).raw
    assert "tenant_id = 't1'" in data_raw["sql"]

    # rag:检索有引用(检索前 ACL 过滤,本租户可见,红线 5)
    rag_raw = session.workspace.get(results["search_knowledge"]).raw
    assert rag_raw["citations"]

    # code:子 Agent 回传结构化证据(红线 12,探索噪音不外传)
    code_raw = session.workspace.get(results["ask_codebase"]).raw
    assert code_raw["evidences"] and code_raw["confidence"] >= 0.5

    # 正常综合作答完成
    answer = "".join(e.text for e in events if isinstance(e, AnswerDeltaEvent))
    assert answer.strip()
    done = [e for e in events if isinstance(e, DoneEvent)]
    assert done[-1].stop_reason == "end_turn"
