"""agent-gateway:会话入口 + SSE 流式(方案 §11.1)。

- POST /chat:鉴权(红线 3)→ 建会话 → Plan&Execute/ReAct → SSE。遇写确认/ask_user 暂停时本段流结束,
  响应头 X-Session-Id 携带会话 ID。
- POST /chat/confirm:回执(确认 / 澄清答案)→ 校验会话归属(红线 3/9)→ 续传 SSE 段。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from contracts import UserCtx
from llm import Provider
from memory_svc import MemoryService
from orchestrator import (
    Orchestrator,
    Session,
    SessionAccessError,
    SessionNotFoundError,
    SessionStore,
    ToolRegistry,
)
from orchestrator.injection import opening_system_prompt
from orchestrator.skills import SkillIndex

from .auth import get_trace_id, require_user_ctx
from .deps import (
    get_memory_service,
    get_provider,
    get_registry,
    get_session_store,
    get_skill_index,
)
from .sse import encode_sse

app = FastAPI(title="资金计划 Agent 网关", version="0.1.0")


class ChatRequest(BaseModel):
    message: str
    page_context: dict[str, Any] | None = None


class ConfirmRequest(BaseModel):
    session_id: str
    confirmation: dict[str, Any] | None = None
    answers: dict[str, Any] | None = None


def _sse_response(stream: AsyncIterator[str], session: Session) -> StreamingResponse:
    return StreamingResponse(
        stream, media_type="text/event-stream", headers={"X-Session-Id": session.session_id}
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(
    body: ChatRequest,
    user_ctx: Annotated[UserCtx, Depends(require_user_ctx)],
    trace_id: Annotated[str, Depends(get_trace_id)],
    provider: Annotated[Provider, Depends(get_provider)],
    registry: Annotated[ToolRegistry, Depends(get_registry)],
    store: Annotated[SessionStore, Depends(get_session_store)],
    memory_service: Annotated[MemoryService, Depends(get_memory_service)],
    skill_index: Annotated[SkillIndex, Depends(get_skill_index)],
) -> StreamingResponse:
    session = store.create(user_ctx=user_ctx, trace_id=trace_id, page_context=body.page_context)
    # 开场注入:画像 + 相关记忆/经验 TopK + Skill 索引(各设 token 上限,§4.3/§6.2/§7.2)。
    injected = await opening_system_prompt(
        user_ctx, memory_service, skill_index, query=body.message
    )
    orchestrator = Orchestrator(
        provider=provider, registry=registry, system_prompt=lambda: injected
    )
    orchestrator.seed_user_message(session, body.message)

    async def event_stream() -> AsyncIterator[str]:
        async for event in orchestrator.advance(session):
            yield encode_sse(event)

    return _sse_response(event_stream(), session)


@app.post("/chat/confirm")
async def chat_confirm(
    body: ConfirmRequest,
    user_ctx: Annotated[UserCtx, Depends(require_user_ctx)],
    provider: Annotated[Provider, Depends(get_provider)],
    registry: Annotated[ToolRegistry, Depends(get_registry)],
    store: Annotated[SessionStore, Depends(get_session_store)],
    memory_service: Annotated[MemoryService, Depends(get_memory_service)],
    skill_index: Annotated[SkillIndex, Depends(get_skill_index)],
) -> StreamingResponse:
    try:
        session = store.get(body.session_id, user_ctx)  # 红线 3/9:校验会话归属
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc
    except SessionAccessError as exc:
        raise HTTPException(status_code=403, detail="session does not belong to caller") from exc

    injected = await opening_system_prompt(user_ctx, memory_service, skill_index)
    orchestrator = Orchestrator(
        provider=provider, registry=registry, system_prompt=lambda: injected
    )

    async def event_stream() -> AsyncIterator[str]:
        async for event in orchestrator.resume(
            session, confirmation=body.confirmation, answers=body.answers
        ):
            yield encode_sse(event)

    return _sse_response(event_stream(), session)


# ── 内嵌前端静态伺服 + SPA 回退(§10;唯一的前端相关后端改动)──────────────────
# web/ 为后端仓内嵌前端(原生 + Alpine,零构建,同源同部署)。API 路由(/chat、
# /chat/confirm、/healthz、未来 /files)已在上方注册并优先;此 GET 捕获路由对 web/ 内
# 真实文件返回该文件,其余回退 index.html(SPA);candidate 必须落在 _WEB_DIR 内(防目录穿越)。
_WEB_DIR = Path(__file__).resolve().parents[4] / "web"

if _WEB_DIR.is_dir():

    @app.get("/{full_path:path}")
    async def serve_web(full_path: str) -> FileResponse:
        candidate = (_WEB_DIR / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(_WEB_DIR)):
            return FileResponse(candidate)
        return FileResponse(_WEB_DIR / "index.html")
