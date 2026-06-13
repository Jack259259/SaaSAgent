"""统一重试 / 超时(指数退避 + asyncio 超时)。供 AnthropicProvider 使用。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    base_delay_s: float = 0.5
    max_delay_s: float = 8.0
    timeout_s: float = 60.0


async def with_retry[T](
    fn: Callable[[], Awaitable[T]],
    config: RetryConfig,
    *,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """调用 fn(),失败按指数退避重试;每次调用受 timeout_s 墙钟限制。"""
    last: Exception | None = None
    for attempt in range(config.max_attempts):
        try:
            return await asyncio.wait_for(fn(), timeout=config.timeout_s)
        except retry_on as exc:
            last = exc
            if attempt + 1 >= config.max_attempts:
                break
            delay = min(config.base_delay_s * (2**attempt), config.max_delay_s)
            if delay > 0:
                await asyncio.sleep(delay)
    assert last is not None  # 循环至少执行一次,last 必非 None
    raise last
