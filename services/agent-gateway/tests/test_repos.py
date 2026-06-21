"""代码仓管理 ops 安全/流程负例:仓名/主机白名单/路径限定/凭据二步流/解压/删除/更新。

git 子进程被 monkeypatch(不打真实网络);解压用真实 safe_extract;索引用真实 index_repos。
"""

from __future__ import annotations

import subprocess
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from agent_gateway import repos

_CloneFn = Callable[[str, str, Path], "subprocess.CompletedProcess[str]"]


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPOS_DIR", str(tmp_path / "repos"))
    monkeypatch.setenv("FP_CODE_INDEX_DB", str(tmp_path / "idx" / "symbols.db"))
    monkeypatch.delenv("FP_REPO_GIT_HOSTS", raising=False)


def _zip(path: Path, entries: list[tuple[str, bytes]]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return path


def _ok_clone(payload: str = "def f():\n    return 1\n") -> _CloneFn:
    def _fake(url: str, branch: str, dest: Path) -> subprocess.CompletedProcess[str]:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "main.py").write_text(payload, encoding="utf-8")
        (dest / ".git").mkdir()  # 用于验证被剥离
        return subprocess.CompletedProcess(["git"], 0, "", "")

    return _fake


def _fail_clone(stderr: str, code: int = 128) -> _CloneFn:
    def _fake(url: str, branch: str, dest: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["git"], code, "", stderr)

    return _fake


# ---- 仓名 / 输入校验 ---------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["a", "a b", "../evil", "a/b", "x" * 65, "你好"])
def test_invalid_name_rejected(bad: str) -> None:
    with pytest.raises(repos.InvalidRepoName):
        repos.clone_repo(bad, "https://github.com/x/y", "main")


def test_non_http_scheme_rejected() -> None:
    with pytest.raises(repos.InvalidInput):
        repos.clone_repo("myrepo", "file:///etc/passwd", "main")


# ---- 主机白名单(red line:仅允许配置主机)------------------------------------ #
def test_host_not_in_allowlist_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_GIT_HOSTS", "github.com,gitlab.internal")
    with pytest.raises(repos.HostNotAllowed):
        repos.clone_repo("myrepo", "https://evil.example/x/y", "main")


def test_host_in_allowlist_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_REPO_GIT_HOSTS", "github.com")
    monkeypatch.setattr(repos, "_run_git_clone", _ok_clone())
    rec = repos.clone_repo("myrepo", "https://github.com/x/y", "main")
    assert rec["source"] == "git" and rec["branch"] == "main"


# ---- 凭据二步流 --------------------------------------------------------------- #
def test_clone_auth_required_then_credentialed(monkeypatch: pytest.MonkeyPatch) -> None:
    # 匿名 clone 失败且判定为需认证 → AuthRequired
    monkeypatch.setattr(
        repos, "_run_git_clone", _fail_clone("fatal: Authentication failed for 'https://h/r'")
    )
    with pytest.raises(repos.AuthRequired):
        repos.clone_repo("myrepo", "https://h.example/r", "main")
    # 带凭据仍失败 → CloneFailed(不再 AuthRequired)
    with pytest.raises(repos.CloneFailed):
        repos.clone_repo("myrepo", "https://h.example/r", "main", username="u", password="p")


def test_clone_non_auth_failure_is_clone_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repos, "_run_git_clone", _fail_clone("fatal: repository not found"))
    with pytest.raises(repos.CloneFailed):
        repos.clone_repo("myrepo", "https://github.com/x/y", "main")


def test_credentialed_url_encodes() -> None:
    u = repos._credentialed_url("https://github.com/x/y.git", "user@corp", "p@ss/word")
    assert u == "https://user%40corp:p%40ss%2Fword@github.com/x/y.git"


# ---- 成功 clone:剥离 .git + 写元数据 + 建索引 -------------------------------- #
def test_clone_success_strips_git_and_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repos, "_run_git_clone", _ok_clone())
    rec = repos.clone_repo("myrepo", "https://github.com/x/y", "dev")
    dest = repos.repos_dir() / "myrepo"
    assert (dest / "main.py").is_file()
    assert not (dest / ".git").exists()  # .git 被剥离
    assert (
        rec["source"] == "git" and rec["url"] == "https://github.com/x/y" and rec["present"] is True
    )
    assert rec["last_stats"]["indexed"] >= 1
    assert any(r["name"] == "myrepo" for r in repos.list_repos())


def test_clone_existing_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repos, "_run_git_clone", _ok_clone())
    repos.clone_repo("myrepo", "https://github.com/x/y", "main")
    with pytest.raises(repos.RepoExists):
        repos.clone_repo("myrepo", "https://github.com/x/y", "main")


# ---- 压缩包仓:新增 / 更新 / 元数据 url+branch 空 ------------------------------ #
def test_add_archive_repo(tmp_path: Path) -> None:
    arc = _zip(tmp_path / "r.zip", [("pkg/main.py", b"def g():\n    return 2\n")])
    rec = repos.add_archive_repo("ziprepo", arc)
    assert rec["source"] == "archive" and rec["url"] == "" and rec["branch"] == ""
    assert (repos.repos_dir() / "ziprepo" / "pkg" / "main.py").is_file()
    assert rec["last_stats"]["indexed"] >= 1


def test_update_archive_repo_swaps(tmp_path: Path) -> None:
    repos.add_archive_repo("ziprepo", _zip(tmp_path / "a.zip", [("old.py", b"x=1\n")]))
    repos.update_archive_repo("ziprepo", _zip(tmp_path / "b.zip", [("new.py", b"y=2\n")]))
    dest = repos.repos_dir() / "ziprepo"
    assert (dest / "new.py").is_file() and not (dest / "old.py").exists()


def test_update_archive_unsafe_keeps_old(tmp_path: Path) -> None:
    repos.add_archive_repo("ziprepo", _zip(tmp_path / "a.zip", [("keep.py", b"x=1\n")]))
    evil = _zip(tmp_path / "evil.zip", [("../escape.py", b"bad")])
    with pytest.raises(repos.ExtractFailed):
        repos.update_archive_repo("ziprepo", evil)
    assert (repos.repos_dir() / "ziprepo" / "keep.py").is_file()  # 旧仓保留


def test_update_missing_repo_rejected() -> None:
    with pytest.raises(repos.RepoNotFound):
        repos.update_git_repo("nope")
    with pytest.raises(repos.RepoNotFound):
        repos.update_archive_repo("nope", Path("x.zip"))


# ---- 删除 --------------------------------------------------------------------- #
def test_delete_repo(tmp_path: Path) -> None:
    repos.add_archive_repo("ziprepo", _zip(tmp_path / "a.zip", [("m.py", b"x=1\n")]))
    repos.delete_repo("ziprepo")
    assert not (repos.repos_dir() / "ziprepo").exists()
    assert not any(r["name"] == "ziprepo" for r in repos.list_repos())


def test_delete_missing_rejected() -> None:
    with pytest.raises(repos.RepoNotFound):
        repos.delete_repo("nope")
