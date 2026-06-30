"""runtime_config 加载器:yml → os.environ(setdefault,OS env 优先)+ 红线 §6 负例。

隔离:autouse 全量快照/恢复 os.environ(loader 的 setdefault 直接改真实 environ,monkeypatch
不负责回滚未触碰的键);各用例用 tmp_path + FP_APP_CONFIG / FP_SECRETS_CONFIG 指向受控文件。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from agent_gateway import runtime_config

# 本测试文件在 services/agent-gateway/tests/ → 仓根是 parents[3]
# (注意:源码 runtime_config.py 多一层 src/agent_gateway/,那边是 parents[4])。
_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _restore_environ() -> Iterator[None]:
    saved = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _point_at(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, app: str, secrets: str = "") -> None:
    """把 app.yml / secrets.yml 写入 tmp 并让 loader 指向它们(secrets 留空 → 指向不存在文件)。"""
    app_path = tmp_path / "app.yml"
    app_path.write_text(app, encoding="utf-8")
    monkeypatch.setenv("FP_APP_CONFIG", str(app_path))
    if secrets:
        sec_path = tmp_path / "secrets.yml"
        sec_path.write_text(secrets, encoding="utf-8")
        monkeypatch.setenv("FP_SECRETS_CONFIG", str(sec_path))
    else:
        monkeypatch.setenv("FP_SECRETS_CONFIG", str(tmp_path / "_absent_secrets.yml"))


def test_flat_keys_written_to_environ(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(monkeypatch, tmp_path, 'FP_KB_GRAPH_ENGINE: "lightrag"\nFP_KB_GRAPH: "0"\n')
    monkeypatch.delenv("FP_KB_GRAPH_ENGINE", raising=False)
    monkeypatch.delenv("FP_KB_GRAPH", raising=False)
    runtime_config.load_config_into_environ()
    assert os.environ["FP_KB_GRAPH_ENGINE"] == "lightrag"
    assert os.environ["FP_KB_GRAPH"] == "0"


def test_os_env_wins_over_yml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(monkeypatch, tmp_path, 'FP_KB_GRAPH_ENGINE: "lightrag"\n')
    monkeypatch.setenv("FP_KB_GRAPH_ENGINE", "mock")  # 真实环境已设 → 优先
    runtime_config.load_config_into_environ()
    assert os.environ["FP_KB_GRAPH_ENGINE"] == "mock"  # setdefault 不覆盖


def test_var_expansion_and_unresolved_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(
        monkeypatch,
        tmp_path,
        'WREN_API_URL: "${MY_WREN_HOST}/api"\nZOEKT_URL: "${UNSET_THING}"\nBUSINESS_API_URL: ""\n',
    )
    monkeypatch.setenv("MY_WREN_HOST", "http://wren:8000")
    for k in ("WREN_API_URL", "ZOEKT_URL", "BUSINESS_API_URL"):
        monkeypatch.delenv(k, raising=False)
    runtime_config.load_config_into_environ()
    assert os.environ["WREN_API_URL"] == "http://wren:8000/api"
    assert "ZOEKT_URL" not in os.environ  # 未解析的 ${...} → 跳过
    assert "BUSINESS_API_URL" not in os.environ  # 空串 → 跳过


def test_bool_and_int_coerced_to_str(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(monkeypatch, tmp_path, "FP_REPO_ADMIN: true\nFP_KB_GRAPH: 1\nFP_KB_GRAPH_X: false\n")
    for k in ("FP_REPO_ADMIN", "FP_KB_GRAPH", "FP_KB_GRAPH_X"):
        monkeypatch.delenv(k, raising=False)
    runtime_config.load_config_into_environ()
    assert os.environ["FP_REPO_ADMIN"] == "1"  # bool True → "1"(不留 "True")
    assert os.environ["FP_KB_GRAPH"] == "1"  # int 1 → "1"
    assert os.environ["FP_KB_GRAPH_X"] == "0"  # bool False → "0"


def test_nested_and_list_values_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(
        monkeypatch, tmp_path, 'SECTION:\n  NESTED: x\nALIST:\n  - a\n  - b\nFP_KB_GRAPH: "1"\n'
    )
    for k in ("SECTION", "ALIST", "NESTED", "FP_KB_GRAPH"):
        monkeypatch.delenv(k, raising=False)
    runtime_config.load_config_into_environ()
    assert "SECTION" not in os.environ and "ALIST" not in os.environ
    assert os.environ["FP_KB_GRAPH"] == "1"


def test_missing_files_are_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FP_APP_CONFIG", str(tmp_path / "absent_app.yml"))
    monkeypatch.setenv("FP_SECRETS_CONFIG", str(tmp_path / "absent_secrets.yml"))
    runtime_config.load_config_into_environ()  # 不应抛异常


def test_loads_both_app_and_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _point_at(
        monkeypatch, tmp_path, 'WREN_API_URL: "http://wren"\n', secrets='LLM_API_KEY: "sk-test"\n'
    )
    monkeypatch.delenv("WREN_API_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    runtime_config.load_config_into_environ()
    assert os.environ["WREN_API_URL"] == "http://wren"
    assert os.environ["LLM_API_KEY"] == "sk-test"


# ── 红线 §6 负例:密钥不入库 ─────────────────────────────────────────────────────
@pytest.mark.skipif(shutil.which("git") is None, reason="git 不可用")
def test_secrets_yml_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "config/secrets.yml"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "config/secrets.yml 必须被 .gitignore 忽略(防误提交密钥)"


def test_committed_config_has_no_real_secrets() -> None:
    app_yml = (_REPO_ROOT / "config" / "app.yml").read_text(encoding="utf-8")
    example = (_REPO_ROOT / "config" / "secrets.yml.example").read_text(encoding="utf-8")
    assert "sk-" not in app_yml and "sk-" not in example  # 无 API key 字面量
    data = yaml.safe_load(example) or {}
    for key in (
        "LLM_API_KEY",
        "DB_DSN_READONLY",
        "NOTIFY_WEBHOOK_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST",
    ):
        assert data.get(key, "") == "", f"{key} 模板值必须为空占位(勿提交真实密钥)"
