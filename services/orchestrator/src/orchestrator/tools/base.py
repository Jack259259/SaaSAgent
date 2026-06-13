"""基础工具第一批 handler(§5.5;均只读或助手域)。

update_plan / ask_user 由编排循环拦截(见 loop.py),不在此注册。
这里实现 5 件经注册表执行的工具:get_page_context / read_workspace / write_workspace /
export_file / parse_user_file。
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from ..registry import ToolOutcome
from ..tool_context import ToolContext

_MAX_FILE_BYTES = 5 * 1024 * 1024  # 文件大小白名单上限(5 MiB)


async def get_page_context(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    """读当前页面结构化上下文,按 fields 投影 + user_ctx 过滤(前端注入,§5.5)。"""
    page = ctx.page_context or {}
    fields = args.get("fields")
    if isinstance(fields, list) and fields:
        selection = {k: page.get(k) for k in fields if k in page}
    else:
        selection = {k: v for k, v in page.items() if k not in ("route", "record_id")}
    out: dict[str, Any] = {"selection": selection}
    if isinstance(page.get("route"), str):
        out["route"] = page["route"]
    if isinstance(page.get("record_id"), str):
        out["record_id"] = page["record_id"]
    summary = f"页面上下文:{sorted(selection)}" if selection else "无页面上下文"
    return ToolOutcome(summary=summary, raw=out)


async def read_workspace(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    """按句柄分页读取工作区大对象(红线 8 的读取面)。"""
    ref = args.get("ref")
    if not isinstance(ref, str):
        return ToolOutcome(summary="缺少 ref", is_error=True)
    page = int(args.get("page", 1))
    page_size = int(args.get("page_size", 2000))
    try:
        result = ctx.workspace.read(ref, page=page, page_size=page_size)
    except KeyError:
        return ToolOutcome(summary=f"工作区无此句柄:{ref}", is_error=True)
    except ValueError as exc:
        return ToolOutcome(summary=str(exc), is_error=True)
    out = {
        "chunk": result.chunk,
        "page": result.page,
        "total_pages": result.total_pages,
        "eof": result.eof,
    }
    return ToolOutcome(summary=f"读取 {ref} 第 {result.page}/{result.total_pages} 页", raw=out)


async def write_workspace(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    """向工作区写笔记 / 草稿(助手域写,虚拟存储、租户隔离)。"""
    key = str(args.get("key", "note"))
    type_ = str(args.get("type", "note"))
    content = args.get("content", "")
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    summary = text[:80]
    ref = ctx.workspace.put(key=key, type=type_, summary=summary, raw=text)
    return ToolOutcome(summary=f"已写入工作区 {ref}", raw={"ref": ref, "summary": summary})


def _to_xlsx_bytes(content: str) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    if sheet is None:  # pragma: no cover — Workbook 总有活动表
        sheet = workbook.create_sheet()
    for line in content.splitlines() or [content]:
        sheet.append([line])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def export_file(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    """生成交付物落工作区。xlsx 用 openpyxl,md 直出,pdf 留接口(TODO)。"""
    fmt = str(args.get("format", "md"))
    source_ref = args.get("source_ref")
    if not isinstance(source_ref, str):
        return ToolOutcome(summary="缺少 source_ref", is_error=True)
    try:
        item = ctx.workspace.get(source_ref)
    except KeyError:
        return ToolOutcome(summary=f"源句柄不存在:{source_ref}", is_error=True)
    content = item.raw if isinstance(item.raw, str) else json.dumps(item.raw, ensure_ascii=False)

    if fmt == "md":
        ref = ctx.workspace.put(key="export.md", type="export", summary="md 导出", raw=content)
    elif fmt == "xlsx":
        ref = ctx.workspace.put(
            key="export.xlsx", type="export", summary="xlsx 导出", raw=_to_xlsx_bytes(content)
        )
    elif fmt == "pdf":
        # TODO(阶段后续):接入 PDF 渲染库;本阶段不选型。
        return ToolOutcome(summary="pdf 导出未实现(TODO 接口)", is_error=True)
    else:
        return ToolOutcome(summary=f"不支持的导出格式:{fmt}", is_error=True)
    return ToolOutcome(summary=f"已导出 {fmt} → {ref}", raw={"ref": ref})


def _read_xlsx_rows(data: bytes) -> list[list[Any]]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet = workbook.active
    if sheet is None:
        return []
    return [list(row) for row in sheet.iter_rows(values_only=True)]


async def parse_user_file(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    """解析用户上传文件入工作区。csv(标准库)/ xlsx(openpyxl)→ 表格句柄;pdf 留接口。"""
    file_ref = args.get("file_ref")
    if not isinstance(file_ref, str):
        return ToolOutcome(summary="缺少 file_ref", is_error=True)
    kind = str(args.get("kind", ""))
    try:
        raw = ctx.workspace.get(file_ref).raw
    except KeyError:
        return ToolOutcome(summary=f"文件句柄不存在:{file_ref}", is_error=True)

    size = len(raw) if isinstance(raw, (str, bytes)) else 0
    if size > _MAX_FILE_BYTES:
        return ToolOutcome(summary="文件超过大小上限", is_error=True)

    if kind == "csv":
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        rows = [list(r) for r in csv.reader(io.StringIO(text))]
        ref = ctx.workspace.put(key="parsed.csv", type="table", summary=f"{len(rows)} 行", raw=rows)
        return ToolOutcome(
            summary=f"解析 csv:{len(rows)} 行 → {ref}",
            raw={"ref": ref, "summary": f"{len(rows)} 行"},
        )
    if kind == "xlsx":
        if not isinstance(raw, bytes):
            return ToolOutcome(summary="xlsx 需要二进制内容", is_error=True)
        rows = _read_xlsx_rows(raw)
        ref = ctx.workspace.put(
            key="parsed.xlsx", type="table", summary=f"{len(rows)} 行", raw=rows
        )
        return ToolOutcome(
            summary=f"解析 xlsx:{len(rows)} 行 → {ref}",
            raw={"ref": ref, "summary": f"{len(rows)} 行"},
        )
    if kind == "pdf":
        # TODO(阶段后续):接入 PDF 文本抽取;本阶段不选型。
        return ToolOutcome(summary="pdf 解析未实现(TODO 接口)", is_error=True)
    return ToolOutcome(summary=f"不支持的文件类型:{kind}", is_error=True)
