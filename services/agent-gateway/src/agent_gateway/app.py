"""agent-gateway:会话入口 + SSE 流式(方案 §11.1)。

- POST /chat:鉴权(红线 3)→ 建会话 → Plan&Execute/ReAct → SSE。遇写确认/ask_user 暂停时本段流结束,
  响应头 X-Session-Id 携带会话 ID。
- POST /chat/confirm:回执(确认 / 澄清答案)→ 校验会话归属(红线 3/9)→ 续传 SSE 段。
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from contracts import UserCtx
from contracts.models import ResultStatus
from llm import Provider
from memory_svc import MemoryService
from orchestrator import (
    Orchestrator,
    Session,
    SessionAccessError,
    SessionNotFoundError,
    SessionStore,
    ToolRegistry,
    emit_audit,
    who_from_user_ctx,
)
from orchestrator.injection import opening_system_prompt
from orchestrator.skills import SkillIndex
from rag_svc import acl as rag_acl

from . import kb, repos
from .auth import get_trace_id, require_kb_admin, require_repo_admin, require_user_ctx
from .deps import (
    get_memory_service,
    get_provider,
    get_registry,
    get_session_store,
    get_skill_index,
)
from .sse import encode_sse

app = FastAPI(title="资金计划 Agent 网关", version="0.1.0")


class ChatRequest(BaseModel):
    message: str
    page_context: dict[str, Any] | None = None


class ConfirmRequest(BaseModel):
    session_id: str
    confirmation: dict[str, Any] | None = None
    answers: dict[str, Any] | None = None


def _sse_response(stream: AsyncIterator[str], session: Session) -> StreamingResponse:
    return StreamingResponse(
        stream, media_type="text/event-stream", headers={"X-Session-Id": session.session_id}
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(
    body: ChatRequest,
    user_ctx: Annotated[UserCtx, Depends(require_user_ctx)],
    trace_id: Annotated[str, Depends(get_trace_id)],
    provider: Annotated[Provider, Depends(get_provider)],
    registry: Annotated[ToolRegistry, Depends(get_registry)],
    store: Annotated[SessionStore, Depends(get_session_store)],
    memory_service: Annotated[MemoryService, Depends(get_memory_service)],
    skill_index: Annotated[SkillIndex, Depends(get_skill_index)],
) -> StreamingResponse:
    session = store.create(user_ctx=user_ctx, trace_id=trace_id, page_context=body.page_context)
    # 开场注入:画像 + 相关记忆/经验 TopK + Skill 索引(各设 token 上限,§4.3/§6.2/§7.2)。
    injected = await opening_system_prompt(
        user_ctx, memory_service, skill_index, query=body.message
    )
    orchestrator = Orchestrator(
        provider=provider, registry=registry, system_prompt=lambda: injected
    )
    orchestrator.seed_user_message(session, body.message)

    async def event_stream() -> AsyncIterator[str]:
        async for event in orchestrator.advance(session):
            yield encode_sse(event)

    return _sse_response(event_stream(), session)


@app.post("/chat/confirm")
async def chat_confirm(
    body: ConfirmRequest,
    user_ctx: Annotated[UserCtx, Depends(require_user_ctx)],
    provider: Annotated[Provider, Depends(get_provider)],
    registry: Annotated[ToolRegistry, Depends(get_registry)],
    store: Annotated[SessionStore, Depends(get_session_store)],
    memory_service: Annotated[MemoryService, Depends(get_memory_service)],
    skill_index: Annotated[SkillIndex, Depends(get_skill_index)],
) -> StreamingResponse:
    try:
        session = store.get(body.session_id, user_ctx)  # 红线 3/9:校验会话归属
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc
    except SessionAccessError as exc:
        raise HTTPException(status_code=403, detail="session does not belong to caller") from exc

    injected = await opening_system_prompt(user_ctx, memory_service, skill_index)
    orchestrator = Orchestrator(
        provider=provider, registry=registry, system_prompt=lambda: injected
    )

    async def event_stream() -> AsyncIterator[str]:
        async for event in orchestrator.resume(
            session, confirmation=body.confirmation, answers=body.answers
        ):
            yield encode_sse(event)

    return _sse_response(event_stream(), session)


# ── 代码仓管理(/admin/repos;内部管理员 + FP_REPO_ADMIN;§12 item3 的 UI 化)──────
# v1 同步执行;git 子进程 / 安全解压 / 进程内索引的硬化见 repos.py。写操作全量审计(红线 3/9)。
_MAX_UPLOAD_BYTES = 300 * 1024 * 1024
_ARCHIVE_EXTS = (".tar.gz", ".tar.bz2", ".tgz", ".tbz2", ".tar", ".zip")


class RepoCloneRequest(BaseModel):
    name: str
    url: str
    branch: str = "main"
    username: str | None = None
    password: str | None = None


class RepoUpdateRequest(BaseModel):
    username: str | None = None
    password: str | None = None


def _repo_audit(user_ctx: UserCtx, trace_id: str, action: str, status: ResultStatus) -> None:
    emit_audit(
        who=who_from_user_ctx(user_ctx),
        tool=f"repo_admin:{action}",
        args_digest="-",  # 不记 url/凭据原文(§6)
        result_status=status,
        trace_id=trace_id,
    )


def _repo_op(
    action: str, user_ctx: UserCtx, trace_id: str, fn: Callable[[], dict[str, Any]]
) -> dict[str, Any] | JSONResponse:
    try:
        result = fn()
    except repos.RepoError as exc:
        _repo_audit(user_ctx, trace_id, action, ResultStatus.error)
        return JSONResponse(
            status_code=exc.http_status, content={"code": exc.code, "message": str(exc)}
        )
    _repo_audit(user_ctx, trace_id, action, ResultStatus.ok)
    return result


@app.get("/admin/repos")
async def repos_list(
    user_ctx: Annotated[UserCtx, Depends(require_repo_admin)],
) -> list[dict[str, Any]]:
    return repos.list_repos()


@app.post("/admin/repos", response_model=None)
async def repos_clone(
    body: RepoCloneRequest,
    user_ctx: Annotated[UserCtx, Depends(require_repo_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
) -> dict[str, Any] | JSONResponse:
    return _repo_op(
        "clone",
        user_ctx,
        trace_id,
        lambda: repos.clone_repo(
            body.name, body.url, body.branch, username=body.username, password=body.password
        ),
    )


@app.post("/admin/repos/{name}/update", response_model=None)
async def repos_update_git(
    name: str,
    body: RepoUpdateRequest,
    user_ctx: Annotated[UserCtx, Depends(require_repo_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
) -> dict[str, Any] | JSONResponse:
    return _repo_op(
        "update",
        user_ctx,
        trace_id,
        lambda: repos.update_git_repo(name, username=body.username, password=body.password),
    )


@app.delete("/admin/repos/{name}", response_model=None)
async def repos_delete(
    name: str,
    user_ctx: Annotated[UserCtx, Depends(require_repo_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
) -> dict[str, Any] | JSONResponse:
    return _repo_op("delete", user_ctx, trace_id, lambda: repos.delete_repo(name))


@app.post("/admin/repos/upload", response_model=None)
async def repos_upload(
    user_ctx: Annotated[UserCtx, Depends(require_repo_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any] | JSONResponse:
    """上传压缩包(新增或替换 archive 仓):前端不解压,后端安全解压(红线 14)。"""
    try:
        repos._validate_name(name)
    except repos.RepoError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"code": exc.code, "message": str(exc)}
        )
    fname = (file.filename or "").lower()
    suffix = next((e for e in _ARCHIVE_EXTS if fname.endswith(e)), None)
    if suffix is None:
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_INPUT", "message": "仅支持 .zip / .tar / .tar.gz / .tar.bz2"},
        )
    tmpdir = Path(tempfile.mkdtemp(prefix="repo-upload-"))
    tmp = tmpdir / ("upload" + suffix)
    try:
        size = 0
        with open(tmp, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > _MAX_UPLOAD_BYTES:
                    return JSONResponse(
                        status_code=413, content={"code": "TOO_LARGE", "message": "压缩包超过上限"}
                    )
                out.write(chunk)
        existing = next((r for r in repos.list_repos() if r["name"] == name), None)
        if existing and existing.get("source") == "git":
            return JSONResponse(
                status_code=409,
                content={"code": "REPO_EXISTS", "message": "该名称为 git 仓,请改用更新或换名"},
            )
        op: Callable[[], dict[str, Any]] = (
            (lambda: repos.update_archive_repo(name, tmp))
            if existing
            else (lambda: repos.add_archive_repo(name, tmp))
        )
        return _repo_op("upload", user_ctx, trace_id, op)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── 知识库管理(/admin/kb;内部管理员 + IT 库细 ACL)──────────────────────────────
# 文档列举/上传/下载 + 入库(ingest)触发。写操作全量审计(红线 3/9);ingest 进程内异步(见 kb.py,
# 无子进程 → 无命令注入)。it_design 库再叠加 is_internal(红线 5/§9.1)。必须注册在下方 SPA
# 捕获路由之前(GET 路由顺序优先)。上传上限 = kb.MAX_DOC_BYTES(单一事实源)。


def _kb_audit(user_ctx: UserCtx, trace_id: str, action: str, status: ResultStatus) -> None:
    emit_audit(
        who=who_from_user_ctx(user_ctx),
        tool=f"kb_admin:{action}",
        args_digest="-",  # 不记文件名原文(§6)
        result_status=status,
        trace_id=trace_id,
    )


def _kb_op[T](
    action: str, user_ctx: UserCtx, trace_id: str, fn: Callable[[], T]
) -> T | JSONResponse:
    try:
        result = fn()
    except kb.KbError as exc:
        _kb_audit(user_ctx, trace_id, action, ResultStatus.error)
        return JSONResponse(
            status_code=exc.http_status, content={"code": exc.code, "message": str(exc)}
        )
    _kb_audit(user_ctx, trace_id, action, ResultStatus.ok)
    return result


def _check_kb_access(kb_name: str, user_ctx: UserCtx, trace_id: str) -> None:
    """IT 设计库细 ACL:仅内部角色(红线 5/§9.1)。其余库放行;库合法性由各 op 校验(→ INVALID_KB)。"""
    if kb_name == rag_acl.KB_IT_DESIGN and not rag_acl.is_internal(user_ctx):
        _kb_audit(user_ctx, trace_id, "access_it_design", ResultStatus.denied)
        raise HTTPException(status_code=403, detail="IT 设计库仅内部角色可访问")


@app.get("/admin/kb/{kb_name}/docs", response_model=None)
async def kb_list_docs(
    kb_name: str,
    user_ctx: Annotated[UserCtx, Depends(require_kb_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
) -> list[dict[str, Any]] | JSONResponse:
    _check_kb_access(kb_name, user_ctx, trace_id)
    return _kb_op("list", user_ctx, trace_id, lambda: kb.list_docs(kb_name))


@app.post("/admin/kb/{kb_name}/upload", response_model=None)
async def kb_upload(
    kb_name: str,
    user_ctx: Annotated[UserCtx, Depends(require_kb_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any] | JSONResponse:
    """上传 .md/.markdown/.txt/.docx(扩展名 + MIME + 大小 + 解析校验)。前端不解析(红线 14)。"""
    _check_kb_access(kb_name, user_ctx, trace_id)
    try:
        kb.validate_kb(kb_name)
        name = kb.sanitize_doc_name(file.filename or "")
    except kb.KbError as exc:
        _kb_audit(user_ctx, trace_id, "upload", ResultStatus.error)
        return JSONResponse(
            status_code=exc.http_status, content={"code": exc.code, "message": str(exc)}
        )
    if not kb.is_allowed_mime(file.content_type):
        _kb_audit(user_ctx, trace_id, "upload", ResultStatus.denied)
        return JSONResponse(
            status_code=400, content={"code": "INVALID_INPUT", "message": "不支持的 MIME 类型"}
        )
    tmpdir = Path(tempfile.mkdtemp(prefix="kb-upload-"))
    tmp = tmpdir / ("upload" + Path(name).suffix)  # 后缀需与目标一致,供 parse_document 分派
    try:
        size = 0
        with open(tmp, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > kb.MAX_DOC_BYTES:
                    _kb_audit(user_ctx, trace_id, "upload", ResultStatus.error)
                    return JSONResponse(
                        status_code=413, content={"code": "TOO_LARGE", "message": "文件超过上限"}
                    )
                out.write(chunk)
        return _kb_op("upload", user_ctx, trace_id, lambda: kb.save_upload(kb_name, name, tmp))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.get("/admin/kb/{kb_name}/docs/{name}/download", response_model=None)
async def kb_download(
    kb_name: str,
    name: str,
    user_ctx: Annotated[UserCtx, Depends(require_kb_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
) -> FileResponse | JSONResponse:
    _check_kb_access(kb_name, user_ctx, trace_id)
    try:
        path = kb.resolve_download(kb_name, name)
    except kb.KbError as exc:
        _kb_audit(user_ctx, trace_id, "download", ResultStatus.error)
        return JSONResponse(
            status_code=exc.http_status, content={"code": exc.code, "message": str(exc)}
        )
    _kb_audit(user_ctx, trace_id, "download", ResultStatus.ok)
    return FileResponse(path, filename=path.name)


@app.post("/admin/kb/{kb_name}/ingest", response_model=None)
async def kb_ingest(
    kb_name: str,
    user_ctx: Annotated[UserCtx, Depends(require_kb_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
) -> dict[str, Any] | JSONResponse:
    _check_kb_access(kb_name, user_ctx, trace_id)
    return _kb_op("ingest", user_ctx, trace_id, lambda: kb.start_ingest(kb_name))


@app.get("/admin/kb/{kb_name}/ingest/status", response_model=None)
async def kb_ingest_status(
    kb_name: str,
    user_ctx: Annotated[UserCtx, Depends(require_kb_admin)],
    trace_id: Annotated[str, Depends(get_trace_id)],
) -> dict[str, Any] | JSONResponse:
    _check_kb_access(kb_name, user_ctx, trace_id)
    return _kb_op("ingest_status", user_ctx, trace_id, lambda: kb.ingest_status(kb_name))


# ── 内嵌前端静态伺服 + SPA 回退(§10;唯一的前端相关后端改动)──────────────────
# web/ 为后端仓内嵌前端(原生 + Alpine,零构建,同源同部署)。API 路由(/chat、
# /chat/confirm、/healthz、未来 /files)已在上方注册并优先;此 GET 捕获路由对 web/ 内
# 真实文件返回该文件,其余回退 index.html(SPA);candidate 必须落在 _WEB_DIR 内(防目录穿越)。
_WEB_DIR = Path(__file__).resolve().parents[4] / "web"

if _WEB_DIR.is_dir():

    @app.get("/{full_path:path}")
    async def serve_web(full_path: str) -> FileResponse:
        candidate = (_WEB_DIR / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(_WEB_DIR)):
            return FileResponse(candidate)
        return FileResponse(_WEB_DIR / "index.html")
