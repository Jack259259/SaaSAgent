"""Skill 索引/加载 + 开场注入(注入内容出现在系统提示且各段不超限)。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path

from contracts import UserCtx
from llm import LlmResponse, Message, MockProvider, ScriptedTurn, StreamEvent, ToolDef
from memory_svc import MemoryService
from orchestrator import Orchestrator, Session, ToolRegistry
from orchestrator.injection import MEMORY_CAP, cap_tokens, opening_system_prompt
from orchestrator.skills import SkillIndex
from orchestrator.tool_context import ToolContext
from orchestrator.tools import make_load_skill_handler
from orchestrator.workspace import Workspace

_SKILLS_DIR = Path(__file__).parents[3] / "assets" / "skills"
_CHARS_PER_TOKEN = 4


def _uc() -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=["*"]
    )


class _CapturingProvider:
    """记录传给 LLM 的 system,用于断言注入内容到达系统提示段。"""

    def __init__(self, inner: MockProvider) -> None:
        self._inner = inner
        self.captured_system = ""

    async def complete(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> LlmResponse:
        self.captured_system = system
        return await self._inner.complete(
            system=system, messages=messages, tools=tools, max_tokens=max_tokens
        )

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDef] = (),
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        self.captured_system = system
        return self._inner.stream(
            system=system, messages=messages, tools=tools, max_tokens=max_tokens
        )


def test_skill_index_loads_demo_and_render_excludes_body() -> None:
    idx = SkillIndex.load(_SKILLS_DIR)
    assert "demo-variance-analysis" in idx.skills
    rendered = idx.render_index()
    assert "demo-variance-analysis" in rendered and "差异分析" in rendered
    assert "query_finance_data" not in rendered  # 索引只含 name+description,不含正文
    body = idx.load_body("demo-variance-analysis")
    assert body is not None and "query_finance_data" in body and "search_knowledge" in body


async def test_load_skill_tool() -> None:
    handler = make_load_skill_handler(SkillIndex.load(_SKILLS_DIR))
    ctx = ToolContext(user_ctx=_uc(), workspace=Workspace(), trace_id="t")
    out = await handler({"name": "demo-variance-analysis"}, ctx)
    assert not out.is_error and "query_finance_data" in out.raw["content"]
    assert (await handler({"name": "nope"}, ctx)).is_error


def test_cap_tokens_truncates() -> None:
    assert len(cap_tokens("字" * 5000, MEMORY_CAP)) <= MEMORY_CAP * _CHARS_PER_TOKEN + 1


async def test_opening_injection_content() -> None:
    mem = MemoryService()
    uc = _uc()
    await mem.save_profile(uc, "偏好:报告用万元、要简洁", importance=0.9)
    await mem.save_episodic(uc, "上次分析了 Q1 执行率差异", importance=0.8)
    prompt = await opening_system_prompt(uc, mem, SkillIndex.load(_SKILLS_DIR), query="执行率差异")
    assert "demo-variance-analysis" in prompt  # Skill 索引
    assert "偏好" in prompt  # 画像
    assert "差异" in prompt  # 记忆


async def test_opening_injection_caps_huge_memory() -> None:
    mem = MemoryService()
    uc = _uc()
    await mem.save_episodic(uc, "差异" * 3000, importance=0.9)  # 超大记忆
    prompt = await opening_system_prompt(uc, mem, SkillIndex.load(_SKILLS_DIR), query="差异")
    assert "…" in prompt  # 被截断
    assert len(prompt) < 8000  # 各段 token 上限 → 总长有界


async def test_injection_reaches_provider_system() -> None:
    mem = MemoryService()
    uc = _uc()
    await mem.save_profile(uc, "偏好:用万元", importance=0.9)
    injected = await opening_system_prompt(uc, mem, SkillIndex.load(_SKILLS_DIR), query="差异")
    provider = _CapturingProvider(MockProvider([ScriptedTurn(text="好的", stop_reason="end_turn")]))
    orch = Orchestrator(provider=provider, registry=ToolRegistry(), system_prompt=lambda: injected)
    session = Session(session_id="s", trace_id="t", user_ctx=uc)
    orch.seed_user_message(session, "分析差异")
    [_ async for _ in orch.advance(session)]
    assert "demo-variance-analysis" in provider.captured_system
    assert "偏好" in provider.captured_system
