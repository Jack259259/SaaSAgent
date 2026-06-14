"""FastAPI 依赖:Provider / ToolRegistry / SessionStore。测试经 app.dependency_overrides 注入。"""

from __future__ import annotations

import os
from pathlib import Path

from code_svc import CodeService
from data_svc import DataService, PostgresExecutor, SemanticLayer, SqlValidator, WrenAdapter
from llm import AnthropicProvider, Provider
from memory_svc import MemoryService
from orchestrator import SessionStore, ToolRegistry, base_tool_handlers
from orchestrator.skills import SkillIndex
from orchestrator.tools import (
    make_ask_codebase_handler,
    make_find_sop_handler,
    make_load_skill_handler,
    make_query_finance_data_handler,
    make_run_sop_handler,
    make_save_memory_handler,
    make_search_knowledge_handler,
    make_search_memory_handler,
)
from rag_svc import RagService
from sop_executor import SopService

# 进程内会话存储单例(阶段 3 内存版;支撑跨请求暂停/恢复)。
_SESSION_STORE = SessionStore()
# 分层记忆服务单例(阶段 9a 内存版;按 tenant+user 隔离)+ 启动构建的 Skill 索引。
_MEMORY_SERVICE = MemoryService()
_SKILL_INDEX = SkillIndex.load()
# 知识库索引根目录(由人工上传 + ingest 构建;空则检索返回"未找到依据")。
_KNOWLEDGE_INDEX_DIR = Path("data/knowledge/.index")
# 代码索引:仓根(人工 clone 到此)+ 符号库(code-index 构建)。
_CODE_REPOS_DIR = Path("data/repos")
_CODE_INDEX_DB = Path("data/code-index/symbols.db")


def get_provider() -> Provider:
    """生产默认:AnthropicProvider(未配置 LLM_API_KEY 时调用即 NOT_CONFIGURED)。"""
    return AnthropicProvider()


def _data_service() -> DataService:
    """生产默认:WrenAdapter(WREN_API_URL)+ 校验层(tables.yaml)+ PostgresExecutor(DB_DSN_READONLY)。

    未配置 WREN_API_URL / DB_DSN_READONLY 时调用即 NOT_CONFIGURED;校验层(红线 6)始终生效。
    """
    return DataService(
        engine=WrenAdapter(),
        validator=SqlValidator(SemanticLayer.load()),
        executor=PostgresExecutor(),
    )


def _code_service() -> CodeService:
    """生产默认:仓根 data/repos + 符号库;ZOEKT_URL 设了走 Zoekt,否则 search_code 回退 ripgrep。"""
    return CodeService.open(
        repos_root=_CODE_REPOS_DIR,
        db_path=_CODE_INDEX_DB,
        zoekt_url=os.environ.get("ZOEKT_URL"),
    )


def get_memory_service() -> MemoryService:
    return _MEMORY_SERVICE


def get_skill_index() -> SkillIndex:
    return _SKILL_INDEX


def get_registry() -> ToolRegistry:
    """生产默认:基础工具 + 全部领域/记忆/技能工具。

    search_knowledge / query_finance_data / ask_codebase / find_sop / run_sop / save_memory /
    search_memory / load_skill(红线 5/6/12/4/9)。
    """
    registry = ToolRegistry()
    rag_service = RagService.from_dir(_KNOWLEDGE_INDEX_DIR)
    sop_service = SopService.open()  # sops_dir=assets/sops;业务 API 经 BUSINESS_API_URL
    run_sop_handler, run_sop_resume = make_run_sop_handler(sop_service)
    handlers = {
        **base_tool_handlers(),
        "search_knowledge": make_search_knowledge_handler(rag_service),
        "query_finance_data": make_query_finance_data_handler(_data_service()),
        "ask_codebase": make_ask_codebase_handler(get_provider(), _code_service()),
        "find_sop": make_find_sop_handler(sop_service),
        "run_sop": run_sop_handler,
        "save_memory": make_save_memory_handler(_MEMORY_SERVICE),
        "search_memory": make_search_memory_handler(_MEMORY_SERVICE),
        "load_skill": make_load_skill_handler(_SKILL_INDEX),
    }
    registry.register_from_contracts(handlers, resumes={"run_sop": run_sop_resume})
    return registry


def get_session_store() -> SessionStore:
    return _SESSION_STORE
