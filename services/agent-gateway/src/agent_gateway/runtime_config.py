"""启动期配置加载:把 config/app.yml(非密钥)+ config/secrets.yml(密钥)写回进程环境。

设计(对齐 docs/deploy.md「配置文件与优先级」):
- 不重写散落的 ``os.environ.get(...)`` 调用点;改为启动期把 yml 的键值 ``setdefault`` 进
  ``os.environ`` —— **真实 OS 环境变量优先**(setdefault 不覆盖),所有现有读取点零改动。
- 优先级:OS env / .env > config/secrets.yml > config/app.yml > 代码默认。
- 密钥不入库(CLAUDE.md §6):config/secrets.yml 已 gitignore,仓内只提交 .example 模板;
  缺文件即静默跳过(CI 常态)。LLM 配置仍归 config/llm.yml(config.py),此处不碰其字段;
  仅把 secrets.yml 的 LLM_API_KEY 写回环境,供 llm.yml 的 ``${LLM_API_KEY}`` 解析。
- 由 app.py 的 lifespan startup 调用一次(早于 load_llm_config / 任何请求;早于各 env 读取)。
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .config import _expand  # ${ENV} 插值 + 空/未解析判空,与 llm.yml 同口径

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _app_config_path() -> Path:
    return Path(os.environ.get("FP_APP_CONFIG") or (_REPO_ROOT / "config" / "app.yml"))


def _secrets_config_path() -> Path:
    return Path(os.environ.get("FP_SECRETS_CONFIG") or (_REPO_ROOT / "config" / "secrets.yml"))


def _resolve(value: object) -> str | None:
    """yml 标量 → 环境变量字符串值;无法用于环境变量(空/未解析/容器类型)→ None(跳过)。

    bool 先行规整为 "1"/"0"(防 yaml 把 ``true`` / ``1`` 解析成 bool/int 后与代码 ``== "1"`` 失配)。
    其余交给 ``_expand``:str() + ${ENV} 插值,空串或未解析的 ``${...}`` 视为未设(返回 None)。
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (dict, list)):
        return None  # 仅接受顶层标量;分节请用注释而非嵌套
    return _expand(value)


def _load_file(path: Path) -> None:
    """读单个 yml,顶层标量键 setdefault 进 os.environ(键名即环境变量名);缺文件/非 dict → no-op。"""
    if not path.is_file():
        return
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        return
    for key, value in loaded.items():
        if not isinstance(key, str):
            continue
        resolved = _resolve(value)
        if resolved is None:
            continue
        os.environ.setdefault(key, resolved)  # OS env 优先:已存在则不覆盖


def load_config_into_environ() -> None:
    """加载 config/app.yml 再 config/secrets.yml 到进程环境(幂等;OS env 优先)。"""
    _load_file(_app_config_path())
    _load_file(_secrets_config_path())
