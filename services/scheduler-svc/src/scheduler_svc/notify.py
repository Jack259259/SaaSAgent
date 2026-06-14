"""模板化通知(方案 §5.5):仅白名单模板 + 订阅制 + 频控(助手域写,不触达业务数据)。"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

from contracts import UserCtx

_DEFAULT_TEMPLATES_DIR = Path("assets/notify-templates")
_DEFAULT_RATE_PER_HOUR = 5
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
_SAFE_ID = re.compile(r"[a-z0-9_-]+")


class TemplateNotFoundError(Exception):
    """模板不在白名单(VALIDATION_FAILED)。"""


class RateLimitedError(Exception):
    """超出频控(RATE_LIMITED)。"""


class ChannelNotConfiguredError(Exception):
    """通道未配置(NOT_CONFIGURED)。"""


class NotifyChannel(Protocol):
    def send(self, *, channel: str, recipient: str, body: str) -> bool: ...


class ConsoleChannel:
    """测试用:记录发送内容,不外发。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, *, channel: str, recipient: str, body: str) -> bool:
        self.sent.append((channel, recipient, body))
        return True


class WebhookChannel:
    def __init__(self, *, url: str | None = None, timeout_s: float = 10.0) -> None:
        self._url = url if url is not None else os.environ.get("NOTIFY_WEBHOOK_URL")
        self._timeout = timeout_s

    def send(self, *, channel: str, recipient: str, body: str) -> bool:
        if not self._url:
            raise ChannelNotConfiguredError("NOTIFY_WEBHOOK_URL 未配置")
        resp = httpx.post(
            self._url,
            json={"channel": channel, "recipient": recipient, "body": body},
            timeout=self._timeout,
        )
        return resp.status_code < 400


class TemplateStore:
    """白名单模板:仅渲染 assets/notify-templates/<id>.md 中存在的模板。"""

    def __init__(self, templates_dir: Path = _DEFAULT_TEMPLATES_DIR) -> None:
        self._dir = templates_dir

    def render(self, template_id: str, params: dict[str, Any]) -> str:
        path = self._dir / f"{template_id}.md"
        if not _SAFE_ID.fullmatch(template_id) or not path.is_file():
            raise TemplateNotFoundError(template_id)  # 非白名单 / 路径穿越
        text = path.read_text("utf-8")
        return _PLACEHOLDER_RE.sub(lambda m: str(params.get(m.group(1), m.group(0))), text)


class RateLimiter:
    def __init__(
        self, *, per_hour: int = _DEFAULT_RATE_PER_HOUR, clock: Callable[[], float] = time.time
    ) -> None:
        self._per_hour = per_hour
        self._clock = clock
        self._hits: dict[tuple[str, str, str], list[float]] = {}

    def check_and_record(self, key: tuple[str, str, str]) -> bool:
        now = self._clock()
        recent = [t for t in self._hits.get(key, []) if t > now - 3600]
        if len(recent) >= self._per_hour:
            self._hits[key] = recent
            return False
        recent.append(now)
        self._hits[key] = recent
        return True


class NotifyService:
    def __init__(
        self,
        *,
        channel: NotifyChannel | None = None,
        templates: TemplateStore | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._channel = channel or ConsoleChannel()
        self._templates = templates or TemplateStore()
        self._rate = rate_limiter or RateLimiter()

    def send(
        self, user_ctx: UserCtx, *, template_id: str, channel: str, params: dict[str, Any]
    ) -> bool:
        body = self._templates.render(template_id, params)  # 白名单校验在此
        if not self._rate.check_and_record((user_ctx.tenant_id, user_ctx.user_id, template_id)):
            raise RateLimitedError(template_id)
        return self._channel.send(channel=channel, recipient=user_ctx.user_id, body=body)
