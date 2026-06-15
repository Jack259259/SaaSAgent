"""全链路可观测(方案 §10.1)。

Tracer 抽象 + 每会话 trace_id 贯穿(contextvar)。默认 LocalTracer(structlog span);
配置 LANGFUSE_* 且 langfuse 可导入时用 LangfuseTracer,否则**静默降级**为本地日志。
packages/llm provider 与 orchestrator ToolRegistry 据此埋 span;span 不记密钥/结果明细。
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any, Protocol

import structlog

_log = structlog.get_logger("trace")
_current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="")
_tracer_singleton: Tracer | None = None


def bind_trace(trace_id: str) -> None:
    """绑定当前执行上下文的 trace_id(orchestrator 在会话推进时调用)。"""
    _current_trace_id.set(trace_id)


def current_trace_id() -> str:
    return _current_trace_id.get()


class Tracer(Protocol):
    def span(
        self, name: str, *, trace_id: str | None = None, **attrs: Any
    ) -> contextlib.AbstractContextManager[None]: ...


class LocalTracer:
    """本地降级:每个 span 结束时记一条结构化日志(span 名 + trace_id + 耗时 + 脱敏属性)。"""

    @contextlib.contextmanager
    def span(self, name: str, *, trace_id: str | None = None, **attrs: Any) -> Iterator[None]:
        tid = trace_id or current_trace_id()
        start = time.monotonic()
        try:
            yield
        finally:
            _log.info(
                "span",
                span=name,
                trace_id=tid,
                duration_ms=round((time.monotonic() - start) * 1000, 1),
                **attrs,
            )


class LangfuseTracer:
    """Langfuse 接入(自托管)。懒加载;构造失败由 get_tracer 兜底为 LocalTracer。"""

    def __init__(self) -> None:
        import langfuse  # 未安装则 ImportError → get_tracer 降级

        self._client = langfuse.Langfuse()

    @contextlib.contextmanager
    def span(self, name: str, *, trace_id: str | None = None, **attrs: Any) -> Iterator[None]:
        tid = trace_id or current_trace_id()
        span = self._client.span(name=name, trace_id=tid or None, metadata=attrs)
        try:
            yield
        finally:
            with contextlib.suppress(Exception):
                span.end()


def get_tracer() -> Tracer:
    if os.environ.get("LANGFUSE_PUBLIC_KEY"):
        try:
            return LangfuseTracer()
        except Exception:  # 任何不可用都静默降级为本地日志
            _log.warning("langfuse_unavailable_fallback_local")
    return LocalTracer()


def tracer() -> Tracer:
    """进程级 Tracer 单例(首次解析后缓存)。"""
    global _tracer_singleton
    if _tracer_singleton is None:
        _tracer_singleton = get_tracer()
    return _tracer_singleton
