"""FastAPI 依赖:Provider / ToolRegistry / SessionStore。测试经 app.dependency_overrides 注入。"""

from __future__ import annotations

from llm import AnthropicProvider, Provider
from orchestrator import SessionStore, ToolRegistry, base_tool_handlers

# 进程内会话存储单例(阶段 3 内存版;支撑跨请求暂停/恢复)。
_SESSION_STORE = SessionStore()


def get_provider() -> Provider:
    """生产默认:AnthropicProvider(未配置 LLM_API_KEY 时调用即 NOT_CONFIGURED)。"""
    return AnthropicProvider()


def get_registry() -> ToolRegistry:
    """生产默认:注册基础工具第一批(get_page_context / read|write_workspace / export / parse)。"""
    registry = ToolRegistry()
    registry.register_from_contracts(base_tool_handlers())
    return registry


def get_session_store() -> SessionStore:
    return _SESSION_STORE
