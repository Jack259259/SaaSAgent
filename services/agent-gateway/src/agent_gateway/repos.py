"""代码仓管理 ops(§12 item3 的 UI 化;内部管理员触发)。v1 同步执行。

安全(对应红线 11/12/14 与 docs/integration/code-repos.md):
- 仅经 `/admin/repos` 端点触发,端点侧 `require_repo_admin` 零信任二次校验 + 审计。
- **git 是唯一子进程**:无 shell、超时、`GIT_TERMINAL_PROMPT=0`(私有仓无凭据即失败而非卡死)、
  `--depth 1 --single-branch`、**主机白名单**(`FP_REPO_GIT_HOSTS`)。私有仓二步式:先匿名 clone,
  失败且判定为"需认证" → `AuthRequired`(前端弹窗收账号密码)→ 带凭据 URL 重试;凭据**不入日志**,
  clone 成功即删 `.git/`(剔除 config 残留凭据 + 省空间;"更新"=重 clone,不需 .git)。
- 解压走 `common.safe_extract`(进程内,防 zip-slip/炸弹/符号链接);索引走 `code_svc.index_repos`
  (进程内,`_index_lock` 串行,避免并发重建竞态)。
- FS 全程限定 `repos_dir()`(realpath 父目录校验,防穿越);仓名 `^[A-Za-z0-9_-]{2,64}$`。
- 元数据 sidecar `repos.json`(不入库;zip 仓 url/branch 空)。
  更新采用临时目录 + 成功才替换,失败保留旧仓。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from code_svc import index_repos
from common.safe_extract import UnsafeArchiveError, safe_extract

_REPO_ROOT = Path(__file__).resolve().parents[4]
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,64}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/+-]{1,128}$")
_CLONE_TIMEOUT_S = 600
_index_lock = threading.Lock()

# git stderr 中"需认证"的判定片段(小写子串)。
_AUTH_HINTS = (
    "authentication failed",
    "could not read username",
    "could not read password",
    "terminal prompts disabled",
    "http basic: access denied",
    "permission denied",
    "fatal: authentication",
    "invalid username or password",
)


class RepoError(Exception):
    code = "REPO_ERROR"
    http_status = 400


class InvalidRepoName(RepoError):
    code = "INVALID_NAME"


class InvalidInput(RepoError):
    code = "INVALID_INPUT"


class HostNotAllowed(RepoError):
    code = "HOST_NOT_ALLOWED"
    http_status = 403


class RepoExists(RepoError):
    code = "REPO_EXISTS"
    http_status = 409


class RepoNotFound(RepoError):
    code = "REPO_NOT_FOUND"
    http_status = 404


class AuthRequired(RepoError):
    code = "AUTH_REQUIRED"
    http_status = 401


class CloneFailed(RepoError):
    code = "CLONE_FAILED"


class ExtractFailed(RepoError):
    code = "EXTRACT_FAILED"


# ── 配置(可经环境变量覆盖,便于测试/部署)─────────────────────────────────────
def repos_dir() -> Path:
    return Path(os.environ.get("FP_REPOS_DIR") or (_REPO_ROOT / "data" / "repos"))


def index_db() -> Path:
    return Path(
        os.environ.get("FP_CODE_INDEX_DB") or (_REPO_ROOT / "data" / "code-index" / "symbols.db")
    )


def meta_path() -> Path:
    return index_db().parent / "repos.json"


def allowed_hosts() -> set[str]:
    raw = os.environ.get("FP_REPO_GIT_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


# ── 校验 / 路径限定 ───────────────────────────────────────────────────────────
def _validate_name(name: str) -> str:
    if not _NAME_RE.match(name or ""):
        raise InvalidRepoName("仓名仅限字母 / 数字 / 下划线 / 连字符,2–64 字符")
    return name


def _validate_branch(branch: str) -> str:
    if not _BRANCH_RE.match(branch or ""):
        raise InvalidInput("分支名非法")
    return branch


def _repo_path(name: str) -> Path:
    _validate_name(name)
    root = repos_dir().resolve()
    target = (root / name).resolve()
    if target.parent != root:  # 防穿越:必须正好是 repos_dir 的直接子目录
        raise InvalidRepoName("非法仓路径")
    return target


def _check_host(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise InvalidInput("仓库地址仅支持 http(s)")
    host = (parts.hostname or "").lower()
    if not host:
        raise InvalidInput("无法解析仓库主机")
    allow = allowed_hosts()
    if allow and host not in allow:
        raise HostNotAllowed(f"主机不在白名单:{host}")
    return host


# ── 元数据 sidecar ────────────────────────────────────────────────────────────
def _load_meta() -> dict[str, dict[str, Any]]:
    p = meta_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_meta(meta: dict[str, dict[str, Any]]) -> None:
    p = meta_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def list_repos() -> list[dict[str, Any]]:
    meta = _load_meta()
    root = repos_dir()
    return [
        {"name": name, "present": (root / name).is_dir(), **m} for name, m in sorted(meta.items())
    ]


# ── 工具 ──────────────────────────────────────────────────────────────────────
def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _cleanup(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _strip_git_dir(dest: Path) -> None:
    _cleanup(dest / ".git")  # 剔除 .git/config 残留凭据;"更新"=重 clone,不需 .git


def _sanitize_git_err(stderr: str) -> str:
    """取末行简短信息;不回显凭据/堆栈(面向用户错误不暴露内部,§6)。"""
    lines = [ln for ln in (stderr or "").strip().splitlines() if ln.strip()]
    return (lines[-1] if lines else "git clone 失败")[:200]


def _is_auth_error(stderr: str) -> bool:
    s = (stderr or "").lower()
    return any(h in s for h in _AUTH_HINTS)


def _credentialed_url(url: str, username: str, password: str) -> str:
    parts = urlsplit(url)
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _run_git_clone(url: str, branch: str, dest: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"  # 不交互;无凭据私有仓快速失败而非卡死
    env["GIT_ASKPASS"] = "echo"  # 兜底:任何 askpass 返回空
    env["GCM_INTERACTIVE"] = "never"
    return subprocess.run(
        ["git", "clone", "--depth", "1", "--single-branch", "-b", branch, url, str(dest)],
        capture_output=True,
        text=True,
        timeout=_CLONE_TIMEOUT_S,
        env=env,
        cwd=str(repos_dir()),
    )


def _clone_into(
    url: str, branch: str, target: Path, username: str | None, password: str | None
) -> None:
    """clone 到全新 target(应不存在);失败抛 AuthRequired/CloneFailed 并清理 target。"""
    _validate_branch(branch)
    _check_host(url)
    repos_dir().mkdir(parents=True, exist_ok=True)
    clone_url = _credentialed_url(url, username, password) if (username and password) else url
    try:
        proc = _run_git_clone(clone_url, branch, target)
    except FileNotFoundError as exc:
        raise CloneFailed("未找到 git 可执行文件") from exc
    except subprocess.TimeoutExpired as exc:
        _cleanup(target)
        raise CloneFailed("git clone 超时") from exc
    if proc.returncode != 0:
        _cleanup(target)
        if not (username and password) and _is_auth_error(proc.stderr):
            raise AuthRequired("仓库需要认证,请提供账号密码")
        raise CloneFailed(_sanitize_git_err(proc.stderr))
    _strip_git_dir(target)


def _reindex() -> dict[str, int]:
    with _index_lock:  # 串行:index_repos 重建整库,禁并发
        return index_repos(repos_root=repos_dir(), db_path=index_db())


# ── 公开操作 ──────────────────────────────────────────────────────────────────
def clone_repo(
    name: str, url: str, branch: str, *, username: str | None = None, password: str | None = None
) -> dict[str, Any]:
    dest = _repo_path(name)
    if dest.exists():
        raise RepoExists(f"仓 {name} 已存在,更新请用 update")
    _clone_into(url, branch, dest, username, password)
    stats = _reindex()
    meta = _load_meta()
    created = meta.get(name, {}).get("created_at", _now())
    rec = {
        "source": "git",
        "url": url,
        "branch": branch,
        "created_at": created,
        "updated_at": _now(),
        "last_stats": stats,
    }
    meta[name] = rec
    _save_meta(meta)
    return {"name": name, "present": True, **rec}


def update_git_repo(
    name: str, *, username: str | None = None, password: str | None = None
) -> dict[str, Any]:
    meta = _load_meta()
    cur = meta.get(name)
    if not cur or cur.get("source") != "git":
        raise RepoNotFound(f"git 仓 {name} 不存在")
    dest = _repo_path(name)
    tmp = dest.parent / (name + ".new")
    _cleanup(tmp)
    _clone_into(cur["url"], cur["branch"], tmp, username, password)  # 失败抛错,旧仓保留
    _cleanup(dest)
    tmp.rename(dest)  # 成功才替换
    stats = _reindex()
    rec = {**cur, "updated_at": _now(), "last_stats": stats}
    meta[name] = rec
    _save_meta(meta)
    return {"name": name, "present": True, **rec}


def add_archive_repo(name: str, archive_path: Path) -> dict[str, Any]:
    dest = _repo_path(name)
    if dest.exists():
        raise RepoExists(f"仓 {name} 已存在,更新请用 update")
    _extract_into(archive_path, dest)
    stats = _reindex()
    meta = _load_meta()
    created = meta.get(name, {}).get("created_at", _now())
    rec = {
        "source": "archive",
        "url": "",
        "branch": "",
        "created_at": created,
        "updated_at": _now(),
        "last_stats": stats,
    }
    meta[name] = rec
    _save_meta(meta)
    return {"name": name, "present": True, **rec}


def update_archive_repo(name: str, archive_path: Path) -> dict[str, Any]:
    meta = _load_meta()
    cur = meta.get(name)
    if not cur or cur.get("source") != "archive":
        raise RepoNotFound(f"压缩包仓 {name} 不存在")
    dest = _repo_path(name)
    tmp = dest.parent / (name + ".new")
    _cleanup(tmp)
    _extract_into(archive_path, tmp)
    _cleanup(dest)
    tmp.rename(dest)
    stats = _reindex()
    rec = {**cur, "updated_at": _now(), "last_stats": stats}
    meta[name] = rec
    _save_meta(meta)
    return {"name": name, "present": True, **rec}


def _extract_into(archive_path: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    try:
        safe_extract(archive_path, target)
    except UnsafeArchiveError as exc:
        _cleanup(target)
        raise ExtractFailed(str(exc)) from exc
    except Exception:
        _cleanup(target)
        raise


def delete_repo(name: str) -> dict[str, Any]:
    dest = _repo_path(name)
    meta = _load_meta()
    if not dest.exists() and name not in meta:
        raise RepoNotFound(f"仓 {name} 不存在")
    _cleanup(dest)
    if name in meta:
        del meta[name]
        _save_meta(meta)
    stats = _reindex()
    return {"name": name, "deleted": True, "last_stats": stats}
