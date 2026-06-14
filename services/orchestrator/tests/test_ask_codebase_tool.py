"""ask_codebase 子 Agent 集成(§5.1 / 红线 12):结构化结论 + 证据;预算超限部分结论。

子 Agent 复用 Orchestrator,经脚本化 MockProvider 驱动:调代码工具 → 末轮输出 JSON →
handler 解析为 {answer, evidences, confidence, followups}。主侧只收结构化输出(探索噪音不外传)。
"""

from __future__ import annotations

import json
from pathlib import Path

from code_svc import CodeService, FileReader, PythonSearch, SymbolStore, index_repos
from contracts import UserCtx
from llm import MockProvider, ScriptedTurn, ToolUseBlock
from orchestrator import ToolContext
from orchestrator.tools import make_ask_codebase_handler
from orchestrator.workspace import Workspace

_SAMPLE = Path(__file__).parents[2] / "code-svc" / "tests" / "fixtures" / "sample_repo"


def _uc() -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["internal_dev"], data_scope={}, permissions=["*"]
    )


def _code_service(tmp_path: Path) -> CodeService:
    db = tmp_path / "symbols.db"
    index_repos(repos_root=_SAMPLE, db_path=db)
    return CodeService(
        repos_root=_SAMPLE,
        store=SymbolStore(db),
        search=PythonSearch(_SAMPLE, [_SAMPLE]),
        reader=FileReader(_SAMPLE),
    )


def _ctx() -> ToolContext:
    return ToolContext(user_ctx=_uc(), workspace=Workspace(), trace_id="t-code")


async def test_find_callers_returns_structured_evidences(tmp_path: Path) -> None:
    code_service = _code_service(tmp_path)
    answer = json.dumps(
        {
            "answer": "safe_div 被 execution_rate 与 variance 调用",
            "evidences": [
                {"file": "calculator.py", "line_range": "6-6", "snippet": "return safe_div(...)"}
            ],
            "confidence": 0.9,
            "followups": [],
        },
        ensure_ascii=False,
    )
    provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="c1", name="find_callers", input={"name": "safe_div"})],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text=answer, stop_reason="end_turn"),
        ]
    )
    handler = make_ask_codebase_handler(provider, code_service)
    outcome = await handler({"question": "safe_div 被谁调用"}, _ctx())
    assert "execution_rate" in outcome.summary
    evidences = outcome.raw["evidences"]
    assert evidences and evidences[0]["file"] == "calculator.py"
    assert evidences[0]["line_range"] and evidences[0]["snippet"]
    assert outcome.raw["confidence"] >= 0.5
    assert not outcome.is_error
    code_service.close()


async def test_module_question_with_references(tmp_path: Path) -> None:
    code_service = _code_service(tmp_path)
    answer = json.dumps(
        {
            "answer": "calculator 模块计算执行率与差异,均依赖 safe_div",
            "evidences": [
                {
                    "file": "calculator.py",
                    "line_range": "5-7",
                    "snippet": "def execution_rate(plan)",
                }
            ],
            "confidence": 0.8,
            "followups": ["可进一步查看 service.py 如何编排"],
        },
        ensure_ascii=False,
    )
    provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[
                    ToolUseBlock(id="m1", name="find_definition", input={"name": "execution_rate"})
                ],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text=answer, stop_reason="end_turn"),
        ]
    )
    handler = make_ask_codebase_handler(provider, code_service)
    outcome = await handler({"question": "calculator 模块做什么"}, _ctx())
    assert "calculator" in outcome.summary
    assert outcome.raw["evidences"][0]["file"] == "calculator.py"
    assert outcome.raw["followups"]
    code_service.close()


async def test_budget_exhausted_returns_partial_with_followups(tmp_path: Path) -> None:
    code_service = _code_service(tmp_path)
    provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="b1", name="find_callers", input={"name": "safe_div"})],
                stop_reason="tool_use",
            ),
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="b2", name="find_callers", input={"name": "safe_div"})],
                stop_reason="tool_use",
            ),
        ]
    )
    handler = make_ask_codebase_handler(provider, code_service, max_tool_calls=1)
    outcome = await handler({"question": "safe_div 被谁调用"}, _ctx())
    assert outcome.raw["followups"]  # 部分结论附后续建议
    assert outcome.raw["confidence"] < 0.5
    assert outcome.raw["evidences"] == []
    code_service.close()
