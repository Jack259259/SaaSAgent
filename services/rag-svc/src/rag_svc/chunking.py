"""文档解析与分块。md(YAML front-matter 元数据 + 正文分块)完整实现;docx/pdf 走分派接口(TODO)。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
_FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class ParsedDoc:
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    match = _FRONT_RE.match(raw)
    if match is None:
        return {}, raw
    return _parse_simple_yaml(match.group(1)), raw[match.end() :]


def _parse_simple_yaml(front: str) -> dict[str, Any]:
    """front-matter 子集解析:`key: scalar` 与 `key: [a, b]`(详见 knowledge-upload.md)。"""
    meta: dict[str, Any] = {}
    for line in front.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [
                item.strip().strip("\"'") for item in value[1:-1].split(",") if item.strip()
            ]
        else:
            meta[key] = value.strip("\"'")
    return meta


def chunk_body(body: str, *, max_chars: int = 600) -> list[tuple[str, str]]:
    """按空行分段并合并到 ~max_chars;返回 (location, text) 列表。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks: list[tuple[str, str]] = []
    buffer = ""
    index = 0
    for para in paragraphs:
        if buffer and len(buffer) + len(para) > max_chars:
            chunks.append((f"段落{index}", buffer))
            index += 1
            buffer = para
        else:
            buffer = f"{buffer}\n\n{para}" if buffer else para
    if buffer:
        chunks.append((f"段落{index}", buffer))
    return chunks


def parse_document(path: Path) -> ParsedDoc | None:
    """解析受支持的文档为 ParsedDoc;不支持的类型(docx/pdf 当前)返回 None。"""
    if path.suffix.lower() in _TEXT_SUFFIXES:
        raw = path.read_text(encoding="utf-8")
        metadata, body = _parse_frontmatter(raw)
        return ParsedDoc(body=body, metadata=metadata)
    # TODO(阶段后续):docx(python-docx,表格保真)、pdf(文本抽取)解析器接入此处分派。
    return None
