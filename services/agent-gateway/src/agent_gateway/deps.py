"""FastAPI 依赖:Provider / ToolRegistry / SessionStore。测试经 app.dependency_overrides 注入。"""

from __future__ import annotations

from pathlib import Path

from llm import AnthropicProvider, Provider
from orchestrator import SessionStore, ToolRegistry, base_tool_handlers
from orchestrator.tools import make_search_knowledge_handler
from rag_svc import RagService

# 进程内会话存储单例(阶段 3 内存版;支撑跨请求暂停/恢复)。
_SESSION_STORE = SessionStore()
# 知识库索引根目录(由人工上传 + ingest 构建;空则检索返回"未找到依据")。
_KNOWLEDGE_INDEX_DIR = Path("data/knowledge/.index")


def get_provider() -> Provider:
    """生产默认:AnthropicProvider(未配置 LLM_API_KEY 时调用即 NOT_CONFIGURED)。"""
    return AnthropicProvider()


def get_registry() -> ToolRegistry:
    """生产默认:基础工具第一批 + 领域工具 search_knowledge(检索前 ACL,红线 5)。"""
    registry = ToolRegistry()
    rag_service = RagService.from_dir(_KNOWLEDGE_INDEX_DIR)
    handlers = {
        **base_tool_handlers(),
        "search_knowledge": make_search_knowledge_handler(rag_service),
    }
    registry.register_from_contracts(handlers)
    return registry


def get_session_store() -> SessionStore:
    return _SESSION_STORE
