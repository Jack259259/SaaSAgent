"""知识库管理 ops(§12 item2 的 UI 化;内部管理员触发)。

管理面端点 /admin/kb/{kb}/* 的后端实现,对齐既有 /admin/repos(repos.py)形态:
- 端点侧 ``require_kb_admin`` 零信任二次校验 + 审计;IT 设计库再叠加 ``acl.is_internal``
  细 ACL(红线 5 / §9.1)——在 app.py 端点层施加。
- 文档落 ``data/knowledge/{business|it-design}/``(对齐 docs/integration/knowledge-upload.md);
  ``it_design`` 库目录名为连字符 ``it-design``。
- ingest **进程内**触发:``asyncio.run(ingest_dir(...))``,**无子进程 / 无 shell**;kb 取自枚举、
  src 取自固定映射 → 从构造上消灭命令注入。后台线程执行,job 注册表供状态轮询;同库串行
  (运行中再次触发 → ``IngestRunning``/409,避免并发重建索引竞态)。
- FS 全程限定 kb 目录:文件名取 basename + 扩展名白名单 + realpath 父目录校验(防穿越);大小上限。
- 解析校验复用 ``rag_svc.chunking.parse_document``(权威,胜过 MIME):损坏 docx / 非 UTF-8 文本即拒。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from llm import MockProvider
from rag_svc import acl
from rag_svc.chunking import parse_document
from rag_svc.ingest import ingest_dir

_REPO_ROOT = Path(__file__).resolve().parents[4]

# kb → 源目录子名(注意:it_design 库目录为连字符 it-design;对齐 knowledge-upload.md)。
KB_DIRS = {acl.KB_BUSINESS: "business", acl.KB_IT_DESIGN: "it-design"}
DOC_EXTS = (".md", ".markdown", ".txt", ".docx")
MAX_DOC_BYTES = 25 * 1024 * 1024  # 上传上限(app.py 流式裁断引用此常量,单一事实源)
_MAX_NAME_LEN = 200

# MIME 软白名单(浏览器口径不一,扩展名 + 解析校验为权威;此处仅拦明显不符)。
_ALLOWED_MIME = frozenset(
    {
        "",
        "application/octet-stream",
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",  # 某些浏览器对 docx 报 zip
    }
)


# ── 错误类(code + http_status,面向用户不泄内部,§6)──────────────────────────────
class KbError(Exception):
    code = "KB_ERROR"
    http_status = 400


class InvalidKb(KbError):
    code = "INVALID_KB"
    http_status = 404


class InvalidName(KbError):
    code = "INVALID_NAME"


class InvalidInput(KbError):
    code = "INVALID_INPUT"


class TooLarge(KbError):
    code = "TOO_LARGE"
    http_status = 413


class DocNotFound(KbError):
    code = "NOT_FOUND"
    http_status = 404


class IngestRunning(KbError):
    code = "INGEST_RUNNING"
    http_status = 409


# ── 配置(env 可覆盖,便于测试/部署)────────────────────────────────────────────
def knowledge_dir() -> Path:
    return Path(os.environ.get("FP_KNOWLEDGE_DIR") or (_REPO_ROOT / "data" / "knowledge"))


def index_dir() -> Path:
    return knowledge_dir() / ".index"


def graph_root() -> Path:
    """知识图谱(LightRAG)根目录;与 deps 图 Provider 读取**同源**(均经此 + graph_working_dir)。"""
    return knowledge_dir() / ".graph"


def validate_kb(kb: str) -> str:
    if kb not in KB_DIRS:
        raise InvalidKb(f"未知知识库:{kb}")
    return kb


def kb_src_dir(kb: str) -> Path:
    return knowledge_dir() / KB_DIRS[validate_kb(kb)]


# ── 工具 ──────────────────────────────────────────────────────────────────────
def _fmt_time(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))


def is_allowed_mime(content_type: str | None) -> bool:
    return (content_type or "").split(";")[0].strip().lower() in _ALLOWED_MIME


# ── 文件名校验 / 路径限定(防穿越)──────────────────────────────────────────────
def sanitize_doc_name(filename: str) -> str:
    """basename + 白名单:拒空 / .. / 分隔符 / 非白名单扩展名 / 超长;允许 unicode 名。"""
    raw = (filename or "").strip()
    name = Path(raw).name  # 去掉任何目录成分
    if not name or name in (".", "..") or name != raw:
        raise InvalidName("文件名非法(不得含路径分隔符)")
    if "/" in name or "\\" in name or "\x00" in name:
        raise InvalidName("文件名非法")
    if len(name) > _MAX_NAME_LEN:
        raise InvalidName("文件名过长")
    if not name.lower().endswith(DOC_EXTS):
        raise InvalidInput("仅支持 .md / .markdown / .txt / .docx")
    return name


def doc_path(kb: str, name: str) -> Path:
    """kb 目录内文档绝对路径;realpath 必须是 kb 目录的直接子文件(防穿越)。"""
    safe = sanitize_doc_name(name)
    root = kb_src_dir(kb).resolve()
    target = (root / safe).resolve()
    if target.parent != root:
        raise InvalidName("非法文档路径")
    return target


# ── 文档列表 / 上传 / 下载 ──────────────────────────────────────────────────────
def _indexed_names(kb: str) -> set[str]:
    """读 index.json 的 file_hashes 键(rel path;顶层文档即文件名);失败回退空集。"""
    p = index_dir() / kb / "index.json"
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    hashes = data.get("file_hashes", {})
    return set(hashes) if isinstance(hashes, dict) else set()


def list_docs(kb: str) -> list[dict[str, Any]]:
    """列 kb 目录**顶层**受支持文档:name / size / mtime / indexed(是否已入库)。"""
    validate_kb(kb)
    root = kb_src_dir(kb)
    indexed = _indexed_names(kb)
    out: list[dict[str, Any]] = []
    if root.is_dir():
        for p in sorted(root.iterdir()):
            if not p.is_file() or not p.name.lower().endswith(DOC_EXTS):
                continue
            st = p.stat()
            out.append(
                {
                    "name": p.name,
                    "size": st.st_size,
                    "mtime": _fmt_time(st.st_mtime),
                    "indexed": p.name in indexed,
                }
            )
    return out


def save_upload(kb: str, filename: str, tmp_path: Path) -> dict[str, Any]:
    """校验并落盘到 kb 目录(覆盖同名=更新)。

    要求 ``tmp_path`` 后缀与目标扩展名一致(端点负责),以便 parse_document 正确分派。
    解析失败(损坏 docx / 非 UTF-8 文本)→ InvalidInput;不在请求里入库(入库经 start_ingest)。
    """
    target = doc_path(kb, filename)
    try:
        parsed = parse_document(tmp_path)
    except (UnicodeDecodeError, ValueError, OSError) as exc:
        raise InvalidInput("文件无法解析(请确认为有效的 UTF-8 文本或 docx)") from exc
    if parsed is None:
        raise InvalidInput("文件无法解析(不支持或已损坏)")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp_path), str(target))
    return {"name": target.name, "size": target.stat().st_size, "indexed": False}


def resolve_download(kb: str, name: str) -> Path:
    """下载用:校验存在 + 防穿越,返回文件路径。"""
    target = doc_path(kb, name)
    if not target.is_file():
        raise DocNotFound(f"文档不存在:{name}")
    return target


# ── ingest job(进程内后台线程 + 状态注册表;同库串行)──────────────────────────
class _IngestJob:
    def __init__(self, kb: str) -> None:
        self.task_id = uuid.uuid4().hex
        self.kb = kb
        self.status = "running"  # running | done | failed
        self.stats: dict[str, int] | None = None
        self.error: str | None = None
        self.started_at = _fmt_time(time.time())
        self.finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "kb": self.kb,
            "status": self.status,
            "started_at": self.started_at,
        }
        if self.stats is not None:
            d["stats"] = self.stats
        if self.error is not None:
            d["error"] = self.error
        if self.finished_at is not None:
            d["finished_at"] = self.finished_at
        return d


_jobs: dict[str, _IngestJob] = {}  # kb -> 最近一次 job
_jobs_lock = threading.Lock()


def _run_ingest(job: _IngestJob) -> None:
    from . import deps  # 延迟导入避免 kb↔deps 环;运行时按引擎决定是否建图

    # lightrag 引擎:在 .index 之外额外(重)建知识图谱(管理面 tenant=None → _global)。
    # 默认/CI(mock)graph_kwargs 为空 → 行为不变。dev_stub 桩无法做实体抽取 → 跳过。
    graph_kwargs: dict[str, Any] = {}
    build_graph = os.environ.get("FP_KB_GRAPH_ENGINE", "mock") == "lightrag"
    if build_graph:
        provider = deps.get_provider()
        if isinstance(provider, MockProvider):
            build_graph = False  # dev_stub:无真实 LLM,跳过建图(避免产出垃圾实体)
        else:
            graph_kwargs = {"graph_dir": graph_root(), "graph_provider": provider}
    try:
        stats = asyncio.run(
            ingest_dir(kb=job.kb, src=kb_src_dir(job.kb), store_dir=index_dir(), **graph_kwargs)
        )
    except Exception as exc:
        with _jobs_lock:
            job.error = str(exc)[:200]
            job.status = "failed"
            job.finished_at = _fmt_time(time.time())
        return
    if build_graph:
        deps.invalidate_kb_graph(job.kb)  # 失效图 Provider 缓存 → 下次查询读新图(前端自动刷新)
    with _jobs_lock:
        job.stats = dict(stats)
        job.status = "done"
        job.finished_at = _fmt_time(time.time())


def start_ingest(kb: str) -> dict[str, Any]:
    """触发后台入库(进程内,无子进程)。同库已在跑 → IngestRunning/409。返回 job 快照。"""
    validate_kb(kb)
    with _jobs_lock:
        cur = _jobs.get(kb)
        if cur is not None and cur.status == "running":
            raise IngestRunning("该知识库正在入库,请稍候")
        job = _IngestJob(kb)
        _jobs[kb] = job
    threading.Thread(target=_run_ingest, args=(job,), daemon=True).start()
    return job.to_dict()


def ingest_status(kb: str) -> dict[str, Any]:
    validate_kb(kb)
    with _jobs_lock:
        cur = _jobs.get(kb)
        return cur.to_dict() if cur is not None else {"kb": kb, "status": "idle"}


def _reset_jobs() -> None:
    """测试用:清空 job 注册表(进程内全局)。"""
    with _jobs_lock:
        _jobs.clear()
