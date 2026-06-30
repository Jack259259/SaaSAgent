"""摄取管线 CLI:`ingest --kb {business|it_design} --src <dir> [--store-dir <dir>]`。

空目录幂等空跑(人工上传前的常态);增量:按文件 sha256 跳过未变更(方案 §5.3)。
LLM/embedding 经 packages/llm 网关(此处用默认 HashingEmbedder;不直连厂商 SDK)。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from llm import HashingEmbedder

from . import acl
from .chunking import chunk_body, parse_document
from .graph import graph_working_dir
from .lightrag_store import LightRagStore
from .models import Chunk
from .store import LocalKnowledgeStore

if TYPE_CHECKING:
    from llm import Provider

_DEFAULT_STORE_DIR = "data/knowledge/.index"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def ingest_dir(
    *,
    kb: str,
    src: Path,
    store_dir: Path,
    tenant: str | None = None,
    graph_dir: Path | None = None,
    graph_provider: Provider | None = None,
) -> dict[str, int]:
    """检索索引:空目录幂等 + sha256 增量;``graph_dir`` 给定(仅 lightrag)时额外全量重建知识图谱。

    ``graph_dir`` / ``graph_provider`` 缺省 None → 现有行为不变(默认/CI/mock 不建图)。
    """
    index_path = store_dir / kb / "index.json"
    store = LocalKnowledgeStore.load(index_path, embedder=HashingEmbedder())

    files = sorted(p for p in src.rglob("*") if p.is_file()) if src.exists() else []
    stats = {"files": len(files), "docs": 0, "chunks_added": 0, "skipped": 0}
    default_tag = "internal" if kb == acl.KB_IT_DESIGN else "public"

    for path in files:
        parsed = parse_document(path)
        if parsed is None:
            continue  # 不支持/损坏的类型(pdf 当前;损坏 docx 等)
        rel = path.relative_to(src).as_posix()
        digest = _sha256(path)
        if store.file_hash(rel) == digest:
            stats["skipped"] += 1
            continue  # 增量:未变更跳过

        meta: dict[str, Any] = parsed.metadata
        raw_tags = meta.get("acl_tags")
        acl_tags = list(raw_tags) if isinstance(raw_tags, list) and raw_tags else [default_tag]
        source = str(meta.get("source") or rel)
        version = str(meta.get("version", "0"))
        effective_date = meta.get("effective_date")
        raw_tenant = meta.get("tenant_id")  # front-matter 覆盖 CLI --tenant;均缺省则全局(None)
        chunk_tenant = str(raw_tenant) if raw_tenant else tenant
        doc_id = f"{kb}:{rel}"

        chunks = [
            Chunk(
                chunk_id=f"{doc_id}:{i}",
                doc_id=doc_id,
                kb=kb,
                source=source,
                location=location,
                text=text,
                acl_tags=acl_tags,
                tenant_id=chunk_tenant,
                version=version,
                effective_date=effective_date if isinstance(effective_date, str) else None,
            )
            for i, (location, text) in enumerate(chunk_body(parsed.body))
        ]
        store.remove_doc(doc_id)  # 重摄取:先清旧 chunk
        await store.insert(chunks)
        store.set_file_hash(rel, digest)
        stats["docs"] += 1
        stats["chunks_added"] += len(chunks)

    store.save(index_path)

    if graph_dir is not None and graph_provider is not None:
        # lightrag 引擎:在检索索引(.index)之外**额外**全量(重)建知识图谱(.graph)。
        # 写入目录经 graph_working_dir 与 LightRagGraphProvider 读取目录同一事实源。
        await _rebuild_graph(
            kb=kb,
            src=src,
            working_dir=graph_working_dir(graph_dir, kb, tenant),
            provider=graph_provider,
        )
    return stats


async def _rebuild_graph(
    *, kb: str, src: Path, working_dir: Path, provider: Provider
) -> None:  # pragma: no cover — 生产路径(LightRAG 未进 CI;镜像 LightRagStore 范式)
    """「重新入库」全量重建:先清旧(rmtree)再把当前全部文档重抽取进 LightRAG 图。

    与检索索引解耦(各自存储),但复用 parse_document / chunk_body 同口径切块;embedding/llm
    经 LightRagStore → packages/llm 网关,不直连厂商 SDK。全量重建保证图==当前文档集(增/改/删
    一致),不依赖 LightRAG 易变的 adelete API;代价为每次重抽取全部文档(增量为后续优化)。
    """
    if working_dir.exists():
        shutil.rmtree(working_dir, ignore_errors=True)  # 先清旧:保证图反映最新文档集
    working_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in src.rglob("*") if p.is_file()) if src.exists() else []
    default_tag = "internal" if kb == acl.KB_IT_DESIGN else "public"
    chunks: list[Chunk] = []
    for path in files:
        parsed = parse_document(path)
        if parsed is None:
            continue  # 不支持/损坏类型(与索引循环同口径)
        rel = path.relative_to(src).as_posix()
        meta: dict[str, Any] = parsed.metadata
        raw_tags = meta.get("acl_tags")
        acl_tags = list(raw_tags) if isinstance(raw_tags, list) and raw_tags else [default_tag]
        source = str(meta.get("source") or rel)
        raw_tenant = meta.get("tenant_id")
        doc_id = f"{kb}:{rel}"
        chunks.extend(
            Chunk(
                chunk_id=f"{doc_id}:{i}",
                doc_id=doc_id,
                kb=kb,
                source=source,
                location=location,
                text=text,
                acl_tags=acl_tags,
                tenant_id=str(raw_tenant) if raw_tenant else None,
            )
            for i, (location, text) in enumerate(chunk_body(parsed.body))
        )
    if chunks:
        store = LightRagStore(
            working_dir=working_dir, embedder=HashingEmbedder(), provider=provider
        )
        await store.insert(chunks)  # LightRAG ainsert:实体/关系抽取建图(经网关 LLM)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest", description="知识库摄取(空目录幂等)")
    parser.add_argument("--kb", required=True, choices=[acl.KB_BUSINESS, acl.KB_IT_DESIGN])
    parser.add_argument("--src", required=True, help="源目录(如 data/knowledge/business)")
    parser.add_argument("--store-dir", default=_DEFAULT_STORE_DIR, help="索引存储根目录")
    parser.add_argument(
        "--tenant", default=None, help="租户私有语料归属 ID(缺省=全局知识,对所有租户可见)"
    )
    args = parser.parse_args(argv)
    stats = asyncio.run(
        ingest_dir(
            kb=args.kb, src=Path(args.src), store_dir=Path(args.store_dir), tenant=args.tenant
        )
    )
    print(f"ingest kb={args.kb} src={args.src}: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
