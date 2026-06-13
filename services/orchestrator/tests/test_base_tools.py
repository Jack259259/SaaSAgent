"""基础工具第一批 handler 单测(§5.5)。"""

from __future__ import annotations

import io
from typing import Any

import pytest
from openpyxl import Workbook

from contracts import UserCtx
from orchestrator import ToolContext, Workspace
from orchestrator.tools import base as base_mod
from orchestrator.tools import (
    export_file,
    get_page_context,
    parse_user_file,
    read_workspace,
    write_workspace,
)


def _uc() -> UserCtx:
    return UserCtx(tenant_id="t1", user_id="u1", roles=["a"], data_scope={}, permissions=["*"])


def _ctx(*, workspace: Workspace | None = None, page: dict[str, Any] | None = None) -> ToolContext:
    return ToolContext(
        user_ctx=_uc(), workspace=workspace or Workspace(), trace_id="t", page_context=page
    )


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_get_page_context_projection_and_filter() -> None:
    ctx = _ctx(page={"route": "/finance/plan", "record_id": "p1", "amount": 100, "secret": "s"})
    out = await get_page_context({"fields": ["amount"]}, ctx)
    assert out.raw["selection"] == {"amount": 100}
    assert out.raw["route"] == "/finance/plan"
    assert out.raw["record_id"] == "p1"

    empty = await get_page_context({}, _ctx())
    assert empty.raw["selection"] == {}


async def test_read_workspace_paginates() -> None:
    ws = Workspace()
    ref = ws.put(key="big", type="sql_result", summary="s", raw="x" * 5000)
    out = await read_workspace({"ref": ref, "page": 1, "page_size": 2000}, _ctx(workspace=ws))
    assert out.raw["total_pages"] == 3
    assert out.raw["eof"] is False
    missing = await read_workspace({"ref": "ws://nope/1"}, _ctx(workspace=ws))
    assert missing.is_error is True


async def test_write_workspace_persists() -> None:
    ws = Workspace()
    ctx = _ctx(workspace=ws)
    out = await write_workspace({"key": "note", "content": "我的草稿"}, ctx)
    ref = out.raw["ref"]
    assert ws.get(ref).raw == "我的草稿"


async def test_export_file_md_xlsx_and_pdf_todo() -> None:
    ws = Workspace()
    src = ws.put(key="src", type="note", summary="s", raw="line1\nline2")
    ctx = _ctx(workspace=ws)

    md = await export_file({"format": "md", "source_ref": src}, ctx)
    assert ws.get(md.raw["ref"]).raw == "line1\nline2"

    xlsx = await export_file({"format": "xlsx", "source_ref": src}, ctx)
    assert isinstance(ws.get(xlsx.raw["ref"]).raw, bytes)

    pdf = await export_file({"format": "pdf", "source_ref": src}, ctx)
    assert pdf.is_error is True  # TODO 接口


async def test_parse_user_file_csv_xlsx_pdf_and_whitelist(monkeypatch: pytest.MonkeyPatch) -> None:
    ws = Workspace()
    ctx = _ctx(workspace=ws)

    csv_ref = ws.put(key="f", type="upload", summary="s", raw="a,b\n1,2")
    csv_out = await parse_user_file({"file_ref": csv_ref, "kind": "csv"}, ctx)
    assert ws.get(csv_out.raw["ref"]).raw == [["a", "b"], ["1", "2"]]

    xlsx_ref = ws.put(key="f2", type="upload", summary="s", raw=_xlsx_bytes([["x", 1], ["y", 2]]))
    xlsx_out = await parse_user_file({"file_ref": xlsx_ref, "kind": "xlsx"}, ctx)
    assert ws.get(xlsx_out.raw["ref"]).raw == [["x", 1], ["y", 2]]

    pdf_ref = ws.put(key="f3", type="upload", summary="s", raw=b"%PDF-1.4")
    pdf_out = await parse_user_file({"file_ref": pdf_ref, "kind": "pdf"}, ctx)
    assert pdf_out.is_error is True  # TODO 接口

    bad = await parse_user_file({"file_ref": csv_ref, "kind": "exe"}, ctx)
    assert bad.is_error is True

    monkeypatch.setattr(base_mod, "_MAX_FILE_BYTES", 3)
    big_ref = ws.put(key="f4", type="upload", summary="s", raw="too long content")
    oversize = await parse_user_file({"file_ref": big_ref, "kind": "csv"}, ctx)
    assert oversize.is_error is True  # 大小白名单
