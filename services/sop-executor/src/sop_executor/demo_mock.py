"""demo/CI 用的极简内存业务 API(ASGI app)。

供 sop-replay(无真实 base_url 时)与测试经 httpx.ASGITransport 调用,无需真实服务器。
路由:POST /items 创建条目;GET /items/{id} 取条目。created_status 可注入以构造 postcondition 负例。
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any


class DemoMockApp:
    def __init__(self, *, created_status: str = "created", post_status: int = 201) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self._created_status = created_status
        self._post_status = post_status
        self._seq = 0

    async def __call__(self, scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:
        body = await _read_body(receive)
        status, payload = self._route(scope["method"], scope["path"], body)
        await _send_json(send, status, payload)

    def _route(self, method: str, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if method == "POST" and path == "/items":
            if self._post_status >= 400:
                return self._post_status, {"error": "conflict"}
            self._seq += 1
            item_id = f"item-{self._seq}"
            item = {
                "id": item_id,
                "name": body.get("name"),
                "amount": body.get("amount"),
                "status": self._created_status,
            }
            self.items[item_id] = item
            return 201, item
        if method == "GET" and path.startswith("/items/"):
            item_id = path.removeprefix("/items/")
            if item_id in self.items:
                return 200, self.items[item_id]
            return 404, {"error": "not_found"}
        return 404, {"error": "no_route"}


async def _read_body(receive: Any) -> dict[str, Any]:
    chunks = b""
    more = True
    while more:
        event = await receive()
        chunks += event.get("body", b"")
        more = event.get("more_body", False)
    if not chunks:
        return {}
    parsed: Any = json.loads(chunks)
    return parsed if isinstance(parsed, dict) else {}


async def _send_json(send: Any, status: int, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": raw})
