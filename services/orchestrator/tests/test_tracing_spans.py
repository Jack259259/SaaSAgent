"""可观测(方案 §10.1):同一 trace_id 贯穿 provider span / 主 Agent 工具 span / 子 Agent 工具 span。

未配置 LANGFUSE_* 时静默降级为 LocalTracer(structlog span),capture_logs 断言 span 与 trace_id。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from code_svc import CodeService, FileReader, PythonSearch, SymbolStore, index_repos
from contracts import UserCtx
from llm import LocalTracer, MockProvider, ScriptedTurn, ToolUseBlock, get_tracer
from orchestrator import Orchestrator, ToolRegistry
from orchestrator.tools import make_ask_codebase_handler

_SAMPLE = Path(__file__).parents[2] / "code-svc" / "tests" / "fixtures" / "sample_repo"
_TRACE = "trace-obs-1"


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


def test_get_tracer_local_when_langfuse_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    assert isinstance(get_tracer(), LocalTracer)  # 未配置 → 本地降级,不报错


def test_local_span_logs_trace_id() -> None:
    with capture_logs() as logs, LocalTracer().span("unit", trace_id="t-x", tool="demo"):
        pass
    spans = [e for e in logs if e.get("event") == "span"]
    assert spans and spans[0]["trace_id"] == "t-x" and spans[0]["span"] == "unit"


async def test_trace_id_spans_main_and_subagent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    code_service = _code_service(tmp_path)
    findings = json.dumps(
        {
            "answer": "safe_div 被 execution_rate 调用",
            "evidences": [],
            "confidence": 0.7,
            "followups": [],
        },
        ensure_ascii=False,
    )
    # 子 Agent 用独立 provider:调代码工具 → 输出 JSON 结论。
    sub_provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[ToolUseBlock(id="c1", name="find_callers", input={"name": "safe_div"})],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text=findings, stop_reason="end_turn"),
        ]
    )
    # 主 Agent:调 ask_codebase(派发子 Agent)→ 作答。
    main_provider = MockProvider(
        [
            ScriptedTurn(
                tool_calls=[
                    ToolUseBlock(
                        id="a1", name="ask_codebase", input={"question": "safe_div 被谁调用"}
                    )
                ],
                stop_reason="tool_use",
            ),
            ScriptedTurn(text="已查明:execution_rate 调用 safe_div。", stop_reason="end_turn"),
        ]
    )
    registry = ToolRegistry()
    registry.register_from_contracts(
        {"ask_codebase": make_ask_codebase_handler(sub_provider, code_service)}
    )
    orch = Orchestrator(provider=main_provider, registry=registry)

    with capture_logs() as logs:
        async for _ in orch.run(user_ctx=_uc(), user_message="safe_div 被谁调用", trace_id=_TRACE):
            pass

    spans = [e for e in logs if e.get("event") == "span"]
    names = {e["span"] for e in spans}
    assert "llm.stream" in names  # provider span
    assert "tool.ask_codebase" in names  # 主 Agent 工具 span
    assert "tool.find_callers" in names  # 子 Agent 工具 span(贯穿同 trace)
    assert spans and all(e["trace_id"] == _TRACE for e in spans)  # 全链路同一 trace_id
    code_service.close()
