"""代码仓管理端点(/admin/repos):功能开关 + 角色门控(红线 3/9)+ 端点流程。

git 子进程 monkeypatch(不打网络);上传用真实 zip + safe_extract + index_repos。
"""

from __future__ import annotations

import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_gateway import repos
from agent_gateway.app import app

_ADMIN = json.dumps(
    {
        "tenant_id": "t",
        "user_id": "u",
        "roles": ["internal_dev"],
        "data_scope": {},
        "permissions": ["*"],
    }
)
_USER = json.dumps(
    {
        "tenant_id": "t",
        "user_id": "u",
        "roles": ["tenant_user"],
        "data_scope": {},
        "permissions": ["*"],
    }
)


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPOS_DIR", str(tmp_path / "repos"))
    monkeypatch.setenv("FP_CODE_INDEX_DB", str(tmp_path / "idx" / "symbols.db"))
    monkeypatch.delenv("FP_REPO_GIT_HOSTS", raising=False)


def _zip_bytes(entries: list[tuple[str, str]]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries:
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def _ok_clone(url: str, branch: str, dest: Path) -> subprocess.CompletedProcess[str]:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "main.py").write_text("x = 1\n", encoding="utf-8")
    return subprocess.CompletedProcess(["git"], 0, "", "")


# ---- 功能开关 + 角色门控(安全) ---------------------------------------------- #
def test_disabled_by_default_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FP_REPO_ADMIN", raising=False)
    r = TestClient(app).get("/admin/repos", headers={"X-User-Ctx": _ADMIN})
    assert r.status_code == 404


def test_non_admin_role_403(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_ADMIN", "1")
    r = TestClient(app).get("/admin/repos", headers={"X-User-Ctx": _USER})
    assert r.status_code == 403


def test_missing_ctx_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_ADMIN", "1")
    r = TestClient(app).get("/admin/repos")
    assert r.status_code == 401


def test_admin_list_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_ADMIN", "1")
    r = TestClient(app).get("/admin/repos", headers={"X-User-Ctx": _ADMIN})
    assert r.status_code == 200 and r.json() == []


# ---- clone 流程 / 错误映射 ---------------------------------------------------- #
def test_clone_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_ADMIN", "1")
    monkeypatch.setattr(repos, "_run_git_clone", _ok_clone)
    r = TestClient(app).post(
        "/admin/repos",
        headers={"X-User-Ctx": _ADMIN},
        json={"name": "demo", "url": "https://github.com/x/y", "branch": "main"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "demo" and body["source"] == "git"


def test_clone_auth_required_maps_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_ADMIN", "1")
    monkeypatch.setattr(
        repos,
        "_run_git_clone",
        lambda u, b, d: subprocess.CompletedProcess(
            ["git"], 128, "", "fatal: Authentication failed"
        ),
    )
    r = TestClient(app).post(
        "/admin/repos",
        headers={"X-User-Ctx": _ADMIN},
        json={"name": "demo", "url": "https://h.example/r", "branch": "main"},
    )
    assert r.status_code == 401 and r.json()["code"] == "AUTH_REQUIRED"


def test_clone_bad_name_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_ADMIN", "1")
    r = TestClient(app).post(
        "/admin/repos",
        headers={"X-User-Ctx": _ADMIN},
        json={"name": "bad name", "url": "https://github.com/x/y", "branch": "main"},
    )
    assert r.status_code == 400 and r.json()["code"] == "INVALID_NAME"


# ---- 上传压缩包(含 zip-slip 负例) ------------------------------------------- #
def test_upload_zip_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_ADMIN", "1")
    r = TestClient(app).post(
        "/admin/repos/upload",
        headers={"X-User-Ctx": _ADMIN},
        data={"name": "ziprepo"},
        files={"file": ("r.zip", _zip_bytes([("pkg/m.py", "y = 2\n")]), "application/zip")},
    )
    assert r.status_code == 200 and r.json()["source"] == "archive"


def test_upload_zip_slip_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_ADMIN", "1")
    r = TestClient(app).post(
        "/admin/repos/upload",
        headers={"X-User-Ctx": _ADMIN},
        data={"name": "ziprepo"},
        files={"file": ("r.zip", _zip_bytes([("../evil.py", "bad")]), "application/zip")},
    )
    assert r.status_code == 400 and r.json()["code"] == "EXTRACT_FAILED"


def test_upload_bad_ext_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_ADMIN", "1")
    r = TestClient(app).post(
        "/admin/repos/upload",
        headers={"X-User-Ctx": _ADMIN},
        data={"name": "ziprepo"},
        files={"file": ("r.rar", io.BytesIO(b"x"), "application/octet-stream")},
    )
    assert r.status_code == 400 and r.json()["code"] == "INVALID_INPUT"


# ---- 删除 --------------------------------------------------------------------- #
def test_delete_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_ADMIN", "1")
    client = TestClient(app)
    client.post(
        "/admin/repos/upload",
        headers={"X-User-Ctx": _ADMIN},
        data={"name": "ziprepo"},
        files={"file": ("r.zip", _zip_bytes([("m.py", "x = 1\n")]), "application/zip")},
    )
    r = client.delete("/admin/repos/ziprepo", headers={"X-User-Ctx": _ADMIN})
    assert r.status_code == 200 and r.json()["deleted"] is True
