"""摄取管线 CLI:`ingest --kb {business|it_design} --src <dir> [--store-dir <dir>]`。

空目录幂等空跑(人工上传前的常态);增量:按文件 sha256 跳过未变更(方案 §5.3)。
LLM/embedding 经 packages/llm 网关(此处用默认 HashingEmbedder;不直连厂商 SDK)。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path
from typing import Any

from llm import HashingEmbedder

from . import acl
from .chunking import chunk_body, parse_document
from .models import Chunk
from .store import LocalKnowledgeStore

_DEFAULT_STORE_DIR = "data/knowledge/.index"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def ingest_dir(*, kb: str, src: Path, store_dir: Path) -> dict[str, int]:
    index_path = store_dir / kb / "index.json"
    store = LocalKnowledgeStore.load(index_path, embedder=HashingEmbedder())

    files = sorted(p for p in src.rglob("*") if p.is_file()) if src.exists() else []
    stats = {"files": len(files), "docs": 0, "chunks_added": 0, "skipped": 0}
    default_tag = "internal" if kb == acl.KB_IT_DESIGN else "public"

    for path in files:
        parsed = parse_document(path)
        if parsed is None:
            continue  # 不支持的类型(docx/pdf 当前)
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
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest", description="知识库摄取(空目录幂等)")
    parser.add_argument("--kb", required=True, choices=[acl.KB_BUSINESS, acl.KB_IT_DESIGN])
    parser.add_argument("--src", required=True, help="源目录(如 data/knowledge/business)")
    parser.add_argument("--store-dir", default=_DEFAULT_STORE_DIR, help="索引存储根目录")
    args = parser.parse_args(argv)
    stats = asyncio.run(ingest_dir(kb=args.kb, src=Path(args.src), store_dir=Path(args.store_dir)))
    print(f"ingest kb={args.kb} src={args.src}: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
