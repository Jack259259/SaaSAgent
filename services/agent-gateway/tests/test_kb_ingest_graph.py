"""ingest↔图 Provider 接缝(不需 LightRAG;均 CI 安全)。

核心断言:ingest 写入图目录 == LightRagGraphProvider 读取图目录(同一 path 事实源),
即「重新入库」建的图正是面板读取的图。另测 graph_root honor FP_KNOWLEDGE_DIR、缓存失效 no-op。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_gateway import deps, kb
from llm import MockProvider
from rag_svc import LightRagGraphProvider, MockGraphProvider, acl, graph_working_dir


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    # 清环境 + 单例,避免跨用例串引擎/串目录。
    monkeypatch.delenv("FP_KB_GRAPH_ENGINE", raising=False)
    monkeypatch.delenv("FP_KNOWLEDGE_DIR", raising=False)
    deps._KB_GRAPH_PROVIDER = None


def test_graph_root_honors_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FP_KNOWLEDGE_DIR", str(tmp_path))
    assert kb.graph_root() == tmp_path / ".graph"


def test_ingest_write_path_matches_provider_read_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # lightrag 下 Provider 读取目录(resolver)必须 == ingest 写入目录(同一 graph_working_dir)。
    monkeypatch.setenv("FP_KNOWLEDGE_DIR", str(tmp_path))
    monkeypatch.setenv("FP_KB_GRAPH_ENGINE", "lightrag")
    monkeypatch.setattr(deps, "get_provider", lambda: MockProvider([]))  # 免真实 LLM 配置

    provider = deps._build_graph_provider()
    assert isinstance(provider, LightRagGraphProvider)
    for kb_name in (acl.KB_BUSINESS, acl.KB_IT_DESIGN):
        read_dir = provider._resolve(kb_name, None)  # Provider 实际读取目录(管理面 tenant=None)
        write_dir = graph_working_dir(kb.graph_root(), kb_name, None)  # ingest 实际写入目录
        assert read_dir == write_dir == tmp_path / ".graph" / kb_name / "_global"


def test_invalidate_kb_graph_mock_engine_noop() -> None:
    # mock 引擎 / Provider 未构建 → invalidate_kb_graph 为 no-op,不抛。
    deps._KB_GRAPH_PROVIDER = None
    deps.invalidate_kb_graph(acl.KB_BUSINESS)  # 未构建 → 安全
    deps._KB_GRAPH_PROVIDER = MockGraphProvider()
    deps.invalidate_kb_graph(acl.KB_BUSINESS)  # mock → no-op,不抛
    deps._KB_GRAPH_PROVIDER = None


async def test_aclose_kb_graph_mock_engine_noop() -> None:
    # 重建前释放句柄:未构建 / mock Provider → aclose_kb_graph 为 no-op,不抛(真实 LightRAG 不进 CI)。
    deps._KB_GRAPH_PROVIDER = None
    await deps.aclose_kb_graph(acl.KB_BUSINESS)  # 未构建 → 安全
    deps._KB_GRAPH_PROVIDER = MockGraphProvider()
    await deps.aclose_kb_graph(acl.KB_BUSINESS)  # mock → no-op,不抛
    deps._KB_GRAPH_PROVIDER = None
