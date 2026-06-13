"""agent-gateway:会话入口 + SSE 流式(方案 §11.1)。

POST /chat:鉴权(红线 3)→ 编排器 ReAct 循环 → SSE 流式事件。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from contracts import UserCtx
from llm import Provider
from orchestrator import Orchestrator, ToolRegistry

from .auth import get_trace_id, require_user_ctx
from .deps import get_provider, get_registry
from .sse import encode_sse

app = FastAPI(title="资金计划 Agent 网关", version="0.1.0")


class ChatRequest(BaseModel):
    message: str
    page_context: dict[str, object] | None = None


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
) -> StreamingResponse:
    orchestrator = Orchestrator(provider=provider, registry=registry)

    async def event_stream() -> AsyncIterator[str]:
        async for event in orchestrator.run(
            user_ctx=user_ctx,
            user_message=body.message,
            trace_id=trace_id,
            page_context=body.page_context,
        ):
            yield encode_sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# /chat/confirm:写操作确认回执端点,阶段 3(Plan&Execute)实现。TODO。
