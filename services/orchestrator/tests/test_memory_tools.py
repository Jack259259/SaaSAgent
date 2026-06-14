"""save_memory / search_memory 工具 handler。"""

from __future__ import annotations

from contracts import UserCtx
from memory_svc import MemoryService
from orchestrator.tool_context import ToolContext
from orchestrator.tools import make_save_memory_handler, make_search_memory_handler
from orchestrator.workspace import Workspace


def _ctx() -> ToolContext:
    uc = UserCtx(tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=["*"])
    return ToolContext(user_ctx=uc, workspace=Workspace(), trace_id="t-mem")


async def test_save_memory_stores_and_threshold() -> None:
    mem = MemoryService()
    save = make_save_memory_handler(mem)
    stored = await save(
        {"content": "偏好:报告用万元", "scope": "preference", "importance": 0.9}, _ctx()
    )
    assert stored.raw["stored"] is True
    low = await save({"content": "随口一提", "importance": 0.1}, _ctx())
    assert low.raw["stored"] is False and "未达" in low.summary


async def test_search_memory_handler() -> None:
    mem = MemoryService()
    ctx = _ctx()
    await mem.save_episodic(ctx.user_ctx, "讨论了资金计划执行率差异", importance=0.8)
    search = make_search_memory_handler(mem)
    out = await search({"query": "执行率", "kinds": ["episodic"]}, ctx)
    assert out.raw["results"] and "执行率" in out.raw["results"][0]["content"]
