"""docx 解析(零依赖 OOXML):段落保序 + 同段多 run 拼接 + 表格转 Markdown;损坏 docx 跳过。"""

from __future__ import annotations

import zipfile
from pathlib import Path

from rag_svc import acl
from rag_svc.chunking import parse_document
from rag_svc.ingest import ingest_dir

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:document xmlns:w="{_W}"><w:body>'
    "<w:p><w:r><w:t>资金计划执行率口径说明。</w:t></w:r></w:p>"
    "<w:p><w:r><w:t>第二段:</w:t></w:r><w:r><w:t>同一段两个 run 拼接。</w:t></w:r></w:p>"
    "<w:tbl>"
    "<w:tr><w:tc><w:p><w:r><w:t>科目</w:t></w:r></w:p></w:tc>"
    "<w:tc><w:p><w:r><w:t>金额</w:t></w:r></w:p></w:tc></w:tr>"
    "<w:tr><w:tc><w:p><w:r><w:t>经营性净流入</w:t></w:r></w:p></w:tc>"
    "<w:tc><w:p><w:r><w:t>1200</w:t></w:r></w:p></w:tc></w:tr>"
    "</w:tbl></w:body></w:document>"
)


def _write_docx(path: Path, document_xml: str = _DOCUMENT_XML) -> Path:
    # 最小 OOXML:解析器仅读 word/document.xml;附 [Content_Types].xml 更接近真实包。
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        zf.writestr("word/document.xml", document_xml)
    return path


def test_docx_paragraphs_and_table(tmp_path: Path) -> None:
    parsed = parse_document(_write_docx(tmp_path / "plan.docx"))
    assert parsed is not None
    body = parsed.body
    assert "资金计划执行率口径说明。" in body
    assert "第二段:同一段两个 run 拼接。" in body  # 同段多 run 拼接
    # 表格转 Markdown(表头 + 分隔行 + 数据行,表格尽量保真)
    assert "| 科目 | 金额 |" in body
    assert "| --- | --- |" in body
    assert "| 经营性净流入 | 1200 |" in body


def test_docx_pipe_escaped(tmp_path: Path) -> None:
    xml = (
        f'<w:document xmlns:w="{_W}"><w:body><w:tbl>'
        "<w:tr><w:tc><w:p><w:r><w:t>a|b</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>c</w:t></w:r></w:p></w:tc></w:tr>"
        "</w:tbl></w:body></w:document>"
    )
    parsed = parse_document(_write_docx(tmp_path / "t.docx", xml))
    assert parsed is not None
    assert r"a\|b" in parsed.body  # 单元格内管道符转义,保 Markdown 表合法


def test_docx_corrupt_returns_none(tmp_path: Path) -> None:
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip at all")
    assert parse_document(bad) is None  # 损坏 docx → 跳过(不中断 ingest 整批)


async def test_ingest_picks_up_docx(tmp_path: Path) -> None:
    src = tmp_path / "business"
    src.mkdir()
    _write_docx(src / "plan.docx")
    (src / "note.md").write_text("# 标题\n\n正文段落。\n", encoding="utf-8")
    stats = await ingest_dir(kb=acl.KB_BUSINESS, src=src, store_dir=tmp_path / ".index")
    assert stats["docs"] == 2  # docx + md 均入库
    assert stats["chunks_added"] >= 2
