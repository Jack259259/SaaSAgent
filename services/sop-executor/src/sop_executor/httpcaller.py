"""HTTP 调用封装(httpx,可注入 client)。

业务系统调用接口化:api 块执行 + preconditions/postconditions 回查都经此。测试注入
`httpx.AsyncClient(transport=ASGITransport(mock_app))` 即可 hermetic,无需真实服务。
"""

from __future__ import annotations

from typing import Any

import httpx


class HttpCaller:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @classmethod
    def for_base_url(cls, base_url: str, *, timeout_s: float = 15.0) -> HttpCaller:
        return cls(httpx.AsyncClient(base_url=base_url, timeout=timeout_s))

    async def call(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> tuple[int, Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = await self._client.request(method, path, json=body, headers=headers)
        try:
            data: Any = resp.json()
        except ValueError:
            data = None
        return resp.status_code, data

    async def aclose(self) -> None:
        await self._client.aclose()
