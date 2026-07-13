"""WrenLocalEngine 单测:MockProvider + FakePlanner 注入,不需要安装 wrenai。

planner 经 WrenPlanner 接缝注入替身;system 提示词从真实 assets(prompts/nl2sql/v1.md +
semantic-layer/wren)组装 —— 同时校验模板渲染与资产可用性。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import httpx
import pytest

from contracts import UserCtx
from data_svc import (
    DataService,
    DuckDBExecutor,
    NotConfiguredError,
    QueryTimeoutError,
    ValidationError,
    WrenLocalEngine,
)
from data_svc.wren_local import extract_clarifications, extract_sql
from llm import (
    LlmResponse,
    Message,
    MockProvider,
    ScriptedTurn,
    StreamEvent,
    TextBlock,
    ToolDef,
)
from llm import NotConfiguredError as LlmNotConfiguredError


def _ctx(tenant: str = "t1") -> UserCtx:
    return UserCtx(tenant_id=tenant, user_id="u", roles=["analyst"], data_scope={})


def _fence(sql: str) -> str:
    return f"```sql\n{sql}\n```"


class FakePlanner:
    """WrenPlanner 替身:前 fail_times 次抛错(错误信息供自纠),之后透传(可加前缀)。"""

    def __init__(
        self, *, fail_times: int = 0, error: str = "planner-boom", prefix: str = ""
    ) -> None:
        self.calls: list[str] = []
        self._fail_times = fail_times
        self._error = error
        self._prefix = prefix

    def plan(self, sql: str) -> str:
        self.calls.append(sql)
        if len(self.calls) <= self._fail_times:
            raise ValueError(self._error)
        return self._prefix + sql


class RecordingProvider(MockProvider):
    """记录每轮收到的 system 与 messages,断言提示词组装与数据位口径。"""

    def __init__(self, turns: Sequence[ScriptedTurn]) -> None:
        super().__init__(turns)
        self.seen: list[list[Message]] = []
        self.last_system = ""

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> LlmResponse:
        self.seen.append(list(messages))
        self.last_system = system
        return await super().complete(
            system=system, messages=messages, tools=tools, max_tokens=max_tokens
        )


class _FailingProvider:
    """complete 固定抛指定异常(NotConfigured / 超时翻译路径)。"""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> LlmResponse:
        raise self._exc

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        raise NotImplementedError


# ---- generate 主流程 ---------------------------------------------------------- #


async def test_happy_path_returns_planned_sql() -> None:
    planner = FakePlanner(prefix="PLANNED: ")
    provider = MockProvider([ScriptedTurn(text=_fence("SELECT plan_id FROM fund_plan"))])
    engine = WrenLocalEngine(provider=provider, planner=planner)
    result = await engine.generate("查计划号", _ctx())
    assert result.sql == "PLANNED: SELECT plan_id FROM fund_plan"
    assert not result.clarifications
    assert engine.name == "wren_local"
    assert planner.calls == ["SELECT plan_id FROM fund_plan"]


async def test_internal_correction_feeds_planner_error_as_data() -> None:
    planner = FakePlanner(fail_times=1, error="table x not in manifest")
    provider = RecordingProvider(
        [
            ScriptedTurn(text=_fence("SELECT bad FROM x")),
            ScriptedTurn(text=_fence("SELECT plan_id FROM fund_plan")),
        ]
    )
    engine = WrenLocalEngine(provider=provider, planner=planner)
    result = await engine.generate("查计划号", _ctx())
    assert result.sql == "SELECT plan_id FROM fund_plan"
    assert planner.calls == ["SELECT bad FROM x", "SELECT plan_id FROM fund_plan"]
    # 第二轮消息含:assistant 原文回放 + planner 错误包裹在 <prior_error> 数据块(user 位)。
    second_round = provider.seen[1]
    texts = [b.text for m in second_round for b in m.content if isinstance(b, TextBlock)]
    joined = "\n".join(texts)
    assert "<prior_error>" in joined and "table x not in manifest" in joined
    assert "table x not in manifest" not in provider.last_system


async def test_internal_correction_exhausted_raises_validation() -> None:
    planner = FakePlanner(fail_times=99)
    provider = MockProvider(
        [ScriptedTurn(text=_fence("SELECT 1 FROM a")), ScriptedTurn(text=_fence("SELECT 2 FROM b"))]
    )
    engine = WrenLocalEngine(provider=provider, planner=planner, max_internal_retries=1)
    with pytest.raises(ValidationError, match="自纠超限"):
        await engine.generate("q", _ctx())
    assert len(planner.calls) == 2  # 初次 + 1 次自纠,不再多调


async def test_clarifications_returned_without_planning() -> None:
    planner = FakePlanner()
    text = (
        '{"clarifications": [{"field": "执行率口径", "question": "按哪种?",'
        ' "options": ["含在途", "不含在途"]}]}'
    )
    engine = WrenLocalEngine(provider=MockProvider([ScriptedTurn(text=text)]), planner=planner)
    result = await engine.generate("执行率怎么算", _ctx())
    assert result.sql is None
    assert [c.field for c in result.clarifications] == ["执行率口径"]
    assert result.clarifications[0].options == ["含在途", "不含在途"]
    assert planner.calls == []  # 澄清路径不触发 planner


async def test_unparseable_output_raises_validation() -> None:
    engine = WrenLocalEngine(
        provider=MockProvider([ScriptedTurn(text="抱歉,我不知道该怎么查")]), planner=FakePlanner()
    )
    with pytest.raises(ValidationError, match="未产出可解析的 SQL"):
        await engine.generate("q", _ctx())


async def test_llm_not_configured_translated() -> None:
    engine = WrenLocalEngine(
        provider=_FailingProvider(LlmNotConfiguredError("no key")), planner=FakePlanner()
    )
    with pytest.raises(NotConfiguredError, match="LLM 未配置"):
        await engine.generate("q", _ctx())


async def test_llm_timeout_translated() -> None:
    engine = WrenLocalEngine(
        provider=_FailingProvider(httpx.ReadTimeout("slow")), planner=FakePlanner()
    )
    with pytest.raises(QueryTimeoutError):
        await engine.generate("q", _ctx())


async def test_missing_project_dir_is_not_configured() -> None:
    engine = WrenLocalEngine(
        provider=MockProvider([ScriptedTurn(text="x")]),
        project_dir=Path("no-such-wren-project"),
        planner=None,  # 惰性构建路径:目录检查先于 wrenai import
    )
    with pytest.raises(NotConfiguredError, match="语义层项目缺失"):
        await engine.generate("q", _ctx())


async def test_prompt_assembly_and_data_positions() -> None:
    provider = RecordingProvider([ScriptedTurn(text=_fence("SELECT plan_id FROM fund_plan"))])
    engine = WrenLocalEngine(provider=provider, planner=FakePlanner())
    await engine.generate("一季度计划金额", _ctx(), prior_error="explain: column not found")
    system = provider.last_system
    # 受控资产进 system:schema(3 表)+ 规则 + few-shot 示例。
    for token in ("fund_plan", "plan_subject", "exec_flow", "业务规则", "示例", "NULLIF"):
        assert token in system
    # 不可信数据只进 user 位,且有分隔标记。
    texts = [b.text for m in provider.seen[0] for b in m.content if isinstance(b, TextBlock)]
    joined = "\n".join(texts)
    assert "<question>" in joined and "一季度计划金额" in joined
    assert "<prior_error>" in joined and "explain: column not found" in joined
    assert "explain: column not found" not in system


async def test_full_chain_with_validator_and_duckdb(executor: DuckDBExecutor) -> None:
    """WrenLocalEngine(Mock) → SqlValidator(RLS 注入) → DuckDBExecutor 全链路。"""
    from data_svc import SemanticLayer, SqlValidator

    engine = WrenLocalEngine(
        provider=MockProvider(
            [ScriptedTurn(text=_fence("SELECT plan_id, plan_amount FROM fund_plan"))]
        ),
        planner=FakePlanner(),
    )
    service = DataService(
        engine=engine,
        validator=SqlValidator(SemanticLayer.load(Path("assets/semantic-layer/tables.yaml"))),
        executor=executor,
    )
    result = await service.query("查全部计划", _ctx("t1"))
    assert "tenant_id = 't1'" in result.sql
    assert result.lineage.engine == "wren_local"
    assert {row[0] for row in result.rows} == {"P1", "P2"}  # conftest 种子中 t2 的 P9 不可见


# ---- 输出解析纯函数 ------------------------------------------------------------ #


@pytest.mark.parametrize(
    "text,expected",
    [
        ("```sql\nSELECT 1 FROM t\n```", "SELECT 1 FROM t"),
        ("说明\n```sql\nSELECT a FROM t;\n```\n完毕", "SELECT a FROM t"),
        ("```sql\nSELECT 1 FROM a\n```\n```sql\nSELECT 2 FROM b\n```", "SELECT 2 FROM b"),
        ("```\nWITH x AS (SELECT 1) SELECT * FROM x\n```", "WITH x AS (SELECT 1) SELECT * FROM x"),
        ("SELECT plan_id FROM fund_plan;", "SELECT plan_id FROM fund_plan"),
        ("with a as (select 1) select * from a", "with a as (select 1) select * from a"),
        ("抱歉,我不知道", None),
        ('```json\n{"a": 1}\n```', None),
        ("", None),
    ],
)
def test_extract_sql(text: str, expected: str | None) -> None:
    assert extract_sql(text) == expected


def test_extract_clarifications_variants() -> None:
    raw = '{"clarifications": [{"field": "f", "question": "q", "options": ["a"], "extra": 1}]}'
    out = extract_clarifications(raw)
    assert len(out) == 1 and out[0].field == "f" and out[0].options == ["a"]

    fenced = f"```json\n{raw}\n```"
    assert len(extract_clarifications(fenced)) == 1

    assert extract_clarifications("SELECT 1") == []
    assert extract_clarifications('{"clarifications": "not-a-list"}') == []
    assert extract_clarifications('{"clarifications": [{"question": "缺 field"}]}') == []
