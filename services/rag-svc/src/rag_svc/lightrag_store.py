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

# 知识图谱实体抽取(LightRAG)给足输出预算:推理型模型(如 deepseek reasoner 系)会先消耗大量
# token 思考,默认 4096 会被截断(finish_reason=length、content 为空)→ 抽不出实体 → 空图。
# max_tokens 是上限不是目标,模型抽完即停,放大不增成本、只防截断。LightRAG 显式给定时以其为准。
_EXTRACT_MAX_TOKENS = 16384


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
            from lightrag import LightRAG  # 可选依赖:uv sync --extra lightrag
            from lightrag.kg.shared_storage import initialize_pipeline_status
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
            max_tokens: int | None = None,
            **_: Any,  # 吞掉 response_format 等(仅 JSON 抽取模式用,当前默认文本模式)
        ) -> str:
            # LightRAG 二次抽取(gleaning)把原文与首轮结果只放在 history_messages 里传入;必须
            # 还原成消息序列置于当前 prompt 之前,否则模型看不到原文 → 只回 <|COMPLETE|>(空抽取)。
            msgs: list[Message] = [
                Message(
                    role=Role.assistant if h.get("role") == "assistant" else Role.user,
                    content=[TextBlock(h.get("content") or "")],
                )
                for h in history_messages or []
            ]
            msgs.append(Message(role=Role.user, content=[TextBlock(prompt)]))
            response = await provider.complete(
                system=system_prompt or "",
                messages=msgs,
                max_tokens=max_tokens or _EXTRACT_MAX_TOKENS,
            )
            return response.text

        # 实体语言默认英文(中文 search gap,见 backend-gaps §I)
        rag = LightRAG(
            working_dir=str(self._working_dir),
            embedding_func=EmbeddingFunc(
                embedding_dim=embedder.dim, max_token_size=8192, func=gateway_embed
            ),
            llm_model_func=gateway_llm,
        )
        await rag.initialize_storages()  # 存储后端(vector / kv / graph / doc-status)
        # 1.x 必需:缺则首次 ainsert 抛 storage_lock 错误
        await initialize_pipeline_status()
        self._rag = rag
        return rag

    async def insert(self, chunks: list[Chunk]) -> None:
        rag = await self._ensure()
        await rag.ainsert([chunk.text for chunk in chunks])

    async def finalize(self) -> None:  # pragma: no cover — 生产路径(真实 LightRAG)
        """落盘并释放 LightRAG 存储句柄;幂等(未初始化即 no-op),释放后置空可重新 _ensure。

        Windows 下重建知识图谱前必须先 finalize 持有该工作目录的实例,否则目录被占用、
        rmtree/rename 失败(见 ingest._rebuild_graph 的临时目录 + 原子替换)。
        """
        rag = self._rag
        if rag is None:
            return
        self._rag = None
        finalize = getattr(rag, "finalize_storages", None)
        if finalize is not None:
            await finalize()

    async def search(
        self, query: str, *, visible: VisiblePredicate, top_k: int
    ) -> list[RetrievedChunk]:
        # 生产化 TODO:ACL 候选过滤须在入库时按库/标签分区(LightRAG 无元数据候选过滤),
        # 再以 QueryParam(mode="mix", only_need_context, include_references) 取回片段并组装引用。
        raise NotImplementedError(
            "LightRagStore.search 待生产化;见 docs/integration/knowledge-upload.md"
        )
