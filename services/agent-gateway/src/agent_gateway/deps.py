"""FastAPI 依赖:Provider / ToolRegistry / SessionStore。测试经 app.dependency_overrides 注入。"""

from __future__ import annotations

import os
from pathlib import Path

from code_svc import CodeService
from data_svc import DataService, PostgresExecutor, SemanticLayer, SqlValidator, WrenAdapter
from llm import (
    AnthropicProvider,
    HashingEmbedder,
    MockProvider,
    OpenAIProvider,
    Provider,
    ScriptedTurn,
)
from memory_svc import MemoryService
from orchestrator import SessionStore, ToolRegistry, base_tool_handlers
from orchestrator.skills import SkillIndex
from orchestrator.tools import (
    make_ask_codebase_handler,
    make_cancel_schedule_handler,
    make_escalate_handler,
    make_find_sop_handler,
    make_list_schedules_handler,
    make_load_skill_handler,
    make_notify_handler,
    make_query_finance_data_handler,
    make_run_sop_handler,
    make_save_memory_handler,
    make_schedule_task_handler,
    make_search_knowledge_handler,
    make_search_memory_handler,
)
from rag_svc import (
    KnowledgeGraphProvider,
    LightRagGraphProvider,
    MockGraphProvider,
    RagService,
    graph_working_dir,
)
from scheduler_svc import (
    EscalationService,
    NotifyService,
    Scheduler,
    SqliteScheduleStore,
    WebhookChannel,
)
from sop_executor import SopService

from .config import load_llm_config
from .kb import graph_root  # 图根单一事实源(与 ingest 写入同源);kb 模块级不反向依赖 deps,无环

# 进程内会话存储单例(阶段 3 内存版;支撑跨请求暂停/恢复)。
_SESSION_STORE = SessionStore()
# 分层记忆服务单例(阶段 9a 内存版;按 tenant+user 隔离)+ 启动构建的 Skill 索引。
_MEMORY_SERVICE = MemoryService()
_SKILL_INDEX = SkillIndex.load()
# 主动性工具单例(阶段 9b):调度(任务表 SQLite;后台轮询 tick 为部署事项,网关只提供工具)、
# 通知(WebhookChannel,NOTIFY_WEBHOOK_URL 未配置即 NOT_CONFIGURED)、转人工(工单落 docs/ops/tickets)。
_SCHEDULER = Scheduler(store=SqliteScheduleStore(Path("data/scheduler/schedules.db")))
_NOTIFY = NotifyService(channel=WebhookChannel())
_ESCALATION = EscalationService()
# 知识库索引根目录(由人工上传 + ingest 构建;空则检索返回"未找到依据")。
_KNOWLEDGE_INDEX_DIR = Path("data/knowledge/.index")
# 知识图谱(LightRAG 生产引擎)按 (kb, tenant) 分目录;根经 kb.graph_root() 与 ingest 写入同源。
_KB_GRAPH_PROVIDER: KnowledgeGraphProvider | None = None
# 代码索引:仓根(人工 clone 到此)+ 符号库(code-index 构建)。
_CODE_REPOS_DIR = Path("data/repos")
_CODE_INDEX_DB = Path("data/code-index/symbols.db")


def get_provider() -> Provider:
    """按 config/llm.yml(路径可经 FP_LLM_CONFIG 覆盖)构造 Provider;缺字段回退同名环境变量。

    dev_stub=true(或 FP_DEV_STUB=1)→ 离线开发桩 MockProvider(无需 api_key);
    否则按 LLM_Interface_Format 选适配器:openai → OpenAIProvider,默认 → AnthropicProvider。
    两种格式共用 model / api_key / base_url(来自配置)。
    """
    cfg = load_llm_config()
    if cfg.dev_stub:
        return MockProvider(
            [
                ScriptedTurn(
                    text=(
                        "你好,这是来自真实 agent-gateway(开发桩 provider,dev_stub)的回答。"
                        "前端经同源 /chat 直连,SSE 字段对齐 docs/dev/sse-protocol.md。"
                    ),
                    stop_reason="end_turn",
                )
            ]
        )
    if cfg.interface_format == "openai":
        return OpenAIProvider(model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url)
    return AnthropicProvider(model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url)


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
    """生产默认:基础工具 + 全部领域/记忆/技能/主动性工具(红线 4/5/6/9/12)。"""
    registry = ToolRegistry()
    rag_service = RagService.from_dir(_KNOWLEDGE_INDEX_DIR)
    sop_service = SopService.open()  # sops_dir=assets/sops;业务 API 经 BUSINESS_API_URL
    run_sop_handler, run_sop_resume = make_run_sop_handler(sop_service)
    schedule_handler, schedule_resume = make_schedule_task_handler(_SCHEDULER)
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
        "schedule_task": schedule_handler,
        "list_schedules": make_list_schedules_handler(_SCHEDULER),
        "cancel_schedule": make_cancel_schedule_handler(_SCHEDULER),
        "notify": make_notify_handler(_NOTIFY),
        "escalate_to_human": make_escalate_handler(_ESCALATION),
    }
    registry.register_from_contracts(
        handlers, resumes={"run_sop": run_sop_resume, "schedule_task": schedule_resume}
    )
    return registry


def get_session_store() -> SessionStore:
    return _SESSION_STORE


def _build_graph_provider() -> KnowledgeGraphProvider:
    """FP_KB_GRAPH_ENGINE 选引擎:默认 ``mock``(CI/无 LightRAG 实例);``lightrag`` → 真实图。

    LightRAG 路径按 (kb, tenant) 分目录物理隔离(红线 9);embedding/llm 经 packages/llm 网关。
    """
    if os.environ.get("FP_KB_GRAPH_ENGINE", "mock") == "lightrag":
        return LightRagGraphProvider(
            # root 与 ingest 同源(kb.graph_root → graph_working_dir)→ 写入/读取路径同一事实源。
            working_dir_resolver=lambda kb, tenant: graph_working_dir(graph_root(), kb, tenant),
            embedder=HashingEmbedder(),
            provider=get_provider(),
        )
    return MockGraphProvider()


def get_kb_graph_service() -> RagService:
    """知识图谱查询用 RagService(仅注图 Provider;不加载检索库)。Provider 单例缓存。"""
    global _KB_GRAPH_PROVIDER
    if _KB_GRAPH_PROVIDER is None:
        _KB_GRAPH_PROVIDER = _build_graph_provider()
    return RagService(stores={}, graph_provider=_KB_GRAPH_PROVIDER)


def invalidate_kb_graph(kb: str, tenant: str | None = None) -> None:
    """ingest(lightrag 引擎)重建图后失效已缓存的图 Provider 实例,使下次查询从新 working_dir 重载。

    mock 引擎 / Provider 尚未构建 → no-op(下次查询复用同一单例 Provider 的缓存)。
    """
    if isinstance(_KB_GRAPH_PROVIDER, LightRagGraphProvider):
        _KB_GRAPH_PROVIDER.invalidate(kb, tenant)
