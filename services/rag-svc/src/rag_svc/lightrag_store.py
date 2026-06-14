"""LightRagStore:生产检索引擎适配器(真 LightRAG)。

要点(要求 1):LightRAG 的 embedding_func / llm_model_func **全部经 packages/llm 网关**
(Embedder / Provider),不直连厂商 SDK,便于成本统计与替换。检索前 ACL 过滤仍由
RagService 入口层负责(LightRAG 无元数据候选过滤,见 docs/integration/knowledge-upload.md)。

本阶段不进单测(库重,需 `pip install lightrag-hku`);默认引擎为 LocalKnowledgeStore。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from llm import Embedder, Message, NotConfiguredError, Provider, Role, TextBlock

from .models import Chunk, RetrievedChunk
from .store import VisiblePredicate


class LightRagStore:
    def __init__(self, *, working_dir: Path, embedder: Embedder, provider: Provider) -> None:
        self._working_dir = working_dir
        self._embedder = embedder
        self._provider = provider
        self._rag: Any = None

    async def _ensure(self) -> Any:
        if self._rag is not None:
            return self._rag
        try:
            from lightrag import LightRAG  # 生产依赖:pip install lightrag-hku
            from lightrag.utils import EmbeddingFunc
        except ImportError as exc:  # pragma: no cover — 生产路径
            raise NotConfiguredError("LightRAG 未安装(pip install lightrag-hku)") from exc

        embedder = self._embedder
        provider = self._provider

        async def gateway_embed(texts: list[str]) -> Any:
            import numpy  # LightRAG 期望 ndarray

            return numpy.array(await embedder.embed(texts))

        async def gateway_llm(
            prompt: str,
            system_prompt: str | None = None,
            history_messages: list[dict[str, str]] | None = None,
            **_: Any,
        ) -> str:
            response = await provider.complete(
                system=system_prompt or "",
                messages=[Message(role=Role.user, content=[TextBlock(prompt)])],
            )
            return response.text

        rag = LightRAG(
            working_dir=str(self._working_dir),
            embedding_func=EmbeddingFunc(
                embedding_dim=embedder.dim, max_token_size=8192, func=gateway_embed
            ),
            llm_model_func=gateway_llm,
        )
        await rag.initialize_storages()
        self._rag = rag
        return rag

    async def insert(self, chunks: list[Chunk]) -> None:
        rag = await self._ensure()
        await rag.ainsert([chunk.text for chunk in chunks])

    async def search(
        self, query: str, *, visible: VisiblePredicate, top_k: int
    ) -> list[RetrievedChunk]:
        # 生产化 TODO:ACL 候选过滤须在入库时按库/标签分区(LightRAG 无元数据候选过滤),
        # 再以 QueryParam(mode="mix", only_need_context, include_references) 取回片段并组装引用。
        raise NotImplementedError(
            "LightRagStore.search 待生产化;见 docs/integration/knowledge-upload.md"
        )
