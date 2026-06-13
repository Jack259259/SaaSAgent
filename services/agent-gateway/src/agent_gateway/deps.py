"""FastAPI 依赖:Provider 与 ToolRegistry。测试经 app.dependency_overrides 注入 Mock。"""

from __future__ import annotations

from llm import AnthropicProvider, Provider
from orchestrator import ToolRegistry


def get_provider() -> Provider:
    """生产默认:AnthropicProvider(未配置 LLM_API_KEY 时调用即 NOT_CONFIGURED)。"""
    return AnthropicProvider()


def get_registry() -> ToolRegistry:
    """生产默认:空注册表(阶段 2 未接入真实能力工具)。"""
    return ToolRegistry()
