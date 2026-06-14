"""NL2SQLEngine 接口 + 两实现:WrenAdapter(生产)/ StubEngine(测试与演示)。

WrenAI 真实 ask 流程更复杂(异步 ask + 轮询),确切契约在 docs/integration/wrenai.md 对接时固定;
本阶段不连接,未配置 WREN_API_URL 即 NOT_CONFIGURED。
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

import httpx

from contracts import UserCtx

from .errors import NotConfiguredError, ValidationError
from .models import Clarification, Nl2SqlResult


@runtime_checkable
class NL2SQLEngine(Protocol):
    @property
    def name(self) -> str: ...

    async def generate(
        self, question: str, user_ctx: UserCtx, *, prior_error: str | None = None
    ) -> Nl2SqlResult: ...


class WrenAdapter:
    """HTTP 调 WrenAI(WREN_API_URL)。transport 可注入,便于离线测试解析逻辑。"""

    def __init__(
        self,
        *,
        api_url: str | None = None,
        timeout_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_url = api_url if api_url is not None else os.environ.get("WREN_API_URL")
        self._timeout = timeout_s
        self._transport = transport

    @property
    def name(self) -> str:
        return "wren"

    async def generate(
        self, question: str, user_ctx: UserCtx, *, prior_error: str | None = None
    ) -> Nl2SqlResult:
        if not self._api_url:
            raise NotConfiguredError("WREN_API_URL 未配置")
        payload: dict[str, str] = {"question": question, "tenant_id": user_ctx.tenant_id}
        if prior_error:
            payload["prior_error"] = prior_error
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            resp = await client.post(f"{self._api_url.rstrip('/')}/v1/ask", json=payload)
            resp.raise_for_status()
            data = resp.json()
        clarifications = data.get("clarifications")
        if clarifications:
            return Nl2SqlResult(clarifications=[Clarification(**c) for c in clarifications])
        sql = data.get("sql")
        if not sql:
            raise ValidationError("WrenAI 未返回 SQL")
        return Nl2SqlResult(sql=str(sql))


class StubEngine:
    """固定映射引擎(测试/演示)。

    mapping: 问句→SQL,或 问句→[第一次, 第二次, …](驱动自纠:首坏后好)。
    clarify: 问句→澄清项(触发 AMBIGUOUS_FIELD)。
    """

    def __init__(
        self,
        mapping: dict[str, str | list[str]] | None = None,
        *,
        clarify: dict[str, list[Clarification]] | None = None,
    ) -> None:
        self._mapping = mapping or {}
        self._clarify = clarify or {}
        self._calls: dict[str, int] = {}

    @property
    def name(self) -> str:
        return "stub"

    async def generate(
        self, question: str, user_ctx: UserCtx, *, prior_error: str | None = None
    ) -> Nl2SqlResult:
        if question in self._clarify:
            return Nl2SqlResult(clarifications=self._clarify[question])
        spec = self._mapping.get(question)
        if spec is None:
            raise ValidationError(f"StubEngine 无此问句映射:{question}")
        if isinstance(spec, str):
            return Nl2SqlResult(sql=spec)
        index = min(self._calls.get(question, 0), len(spec) - 1)
        self._calls[question] = index + 1
        return Nl2SqlResult(sql=spec[index])
