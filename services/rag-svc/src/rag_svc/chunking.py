"""文档解析与分块。md(YAML front-matter)+ docx(零依赖 OOXML)完整实现;pdf 走分派接口(TODO)。"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
_DOCX_SUFFIX = ".docx"
_FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# OOXML(WordprocessingML)主命名空间;ElementTree 以 {ns}tag 形式匹配。
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


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


def _docx_paragraph_text(p: ET.Element) -> str:
    """拼接一个 <w:p> 下所有文本:<w:t> 原文,<w:tab>→制表符,<w:br>/<w:cr>→换行。"""
    parts: list[str] = []
    for node in p.iter():
        if node.tag == f"{_W}t":
            parts.append(node.text or "")
        elif node.tag == f"{_W}tab":
            parts.append("\t")
        elif node.tag in (f"{_W}br", f"{_W}cr"):
            parts.append("\n")
    return "".join(parts)


def _docx_cell_text(tc: ET.Element) -> str:
    """单元格(<w:tc>)文本:其内多段以空格连接,转义管道符、压平换行(保 Markdown 表合法)。"""
    paras = [_docx_paragraph_text(p).strip() for p in tc.findall(f"{_W}p")]
    text = " ".join(s for s in paras if s)
    return text.replace("|", r"\|").replace("\n", " ").strip()


def _docx_table_markdown(tbl: ET.Element) -> str:
    """<w:tbl> → Markdown 表格(首行为表头);空表返回空串(尽量保真)。"""
    rows = [[_docx_cell_text(tc) for tc in tr.findall(f"{_W}tc")] for tr in tbl.findall(f"{_W}tr")]
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(norm[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in norm[1:]]
    return "\n".join(lines)


def _docx_to_text(path: Path) -> str:
    """.docx(OOXML)→ 纯文本 + 表格(Markdown)。零依赖(stdlib zipfile + ElementTree)。

    读 word/document.xml,遍历 <w:body> 直接子节点**保序**(段落与表格交错);
    复杂特性(图片/文本框/批注)忽略——满足检索分块即可。段落/表格间以空行分隔,
    直接喂给 chunk_body()。
    """
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    body = ET.fromstring(xml).find(f"{_W}body")
    if body is None:
        return ""
    blocks: list[str] = []
    for el in body:
        if el.tag == f"{_W}p":
            text = _docx_paragraph_text(el).strip()
            if text:
                blocks.append(text)
        elif el.tag == f"{_W}tbl":
            table = _docx_table_markdown(el)
            if table:
                blocks.append(table)
    return "\n\n".join(blocks)


def parse_document(path: Path) -> ParsedDoc | None:
    """解析受支持的文档为 ParsedDoc;不支持/损坏的类型返回 None(ingest 跳过该文件)。"""
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        raw = path.read_text(encoding="utf-8")
        metadata, body = _parse_frontmatter(raw)
        return ParsedDoc(body=body, metadata=metadata)
    if suffix == _DOCX_SUFFIX:
        # docx 无 front-matter;元数据取库默认(ingest 侧)。损坏 docx→None(上传时已前置校验)。
        try:
            return ParsedDoc(body=_docx_to_text(path), metadata={})
        except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError):
            return None
    # TODO(阶段后续):pdf(文本抽取)解析器接入此处分派。
    return None
