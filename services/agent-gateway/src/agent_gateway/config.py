"""LLM 配置加载:config/llm.yml(路径可经 FP_LLM_CONFIG 覆盖)。

值支持 ${ENV} 插值;缺文件或缺字段回退同名环境变量(向后兼容旧的纯环境变量配置)。
密钥不入库(CLAUDE.md §6):真实 config/llm.yml 已 gitignore,仓内只提交 config/llm.yml.example 模板。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class LlmConfig:
    api_key: str | None
    model: str
    base_url: str | None
    dev_stub: bool


def _expand(value: Any) -> str | None:
    """${ENV} 插值;空串或未解析的 ${...} 视为未设。"""
    if value is None:
        return None
    s = os.path.expandvars(str(value)).strip()
    if not s or s.startswith("${"):
        return None
    return s


def load_llm_config() -> LlmConfig:
    """读取 config/llm.yml + 环境变量回退,返回 LlmConfig。"""
    path = Path(os.environ.get("FP_LLM_CONFIG") or (_REPO_ROOT / "config" / "llm.yml"))
    data: dict[str, Any] = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            data = loaded

    api_key = _expand(data.get("api_key")) or os.environ.get("LLM_API_KEY") or None
    model = _expand(data.get("model")) or os.environ.get("LLM_MODEL") or "claude-opus-4-8"
    base_url = (
        _expand(data.get("url"))
        or os.environ.get("LLM_BASE_URL")
        or os.environ.get("ANTHROPIC_BASE_URL")
        or None
    )
    dev_stub = bool(data.get("dev_stub", False)) or os.environ.get("FP_DEV_STUB") == "1"
    return LlmConfig(api_key=api_key, model=model, base_url=base_url, dev_stub=dev_stub)
