"""LLM_Interface_Format 配置解析与工厂选择:缺省默认 Anthropic、大小写不敏感、非法值清晰报错。"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_gateway import deps
from agent_gateway.config import load_llm_config
from llm import AnthropicProvider, OpenAIProvider

# 隔离用:这些环境变量会干扰配置解析,逐项清空,确保测试只看临时 yml。
_ENV_KEYS = (
    "LLM_INTERFACE_FORMAT",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "ANTHROPIC_BASE_URL",
    "OPENAI_BASE_URL",
    "FP_DEV_STUB",
)


def _write_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "llm.yml"
    path.write_text(body, encoding="utf-8")
    monkeypatch.setenv("FP_LLM_CONFIG", str(path))


def test_missing_field_defaults_to_anthropic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_cfg(tmp_path, monkeypatch, 'api_key: "k"\nmodel: "m"\n')
    assert load_llm_config().interface_format == "anthropic"


def test_empty_field_defaults_to_anthropic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_cfg(tmp_path, monkeypatch, 'LLM_Interface_Format: ""\napi_key: "k"\n')
    assert load_llm_config().interface_format == "anthropic"


@pytest.mark.parametrize("value", ["OpenAI", "openai", "OPENAI", "  OpenAI  "])
def test_openai_value_normalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _write_cfg(tmp_path, monkeypatch, f'LLM_Interface_Format: "{value}"\napi_key: "k"\n')
    assert load_llm_config().interface_format == "openai"


@pytest.mark.parametrize("value", ["Anthropic", "anthropic", "ANTHROPIC"])
def test_anthropic_value_normalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _write_cfg(tmp_path, monkeypatch, f'LLM_Interface_Format: "{value}"\napi_key: "k"\n')
    assert load_llm_config().interface_format == "anthropic"


def test_invalid_value_raises_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_cfg(tmp_path, monkeypatch, 'LLM_Interface_Format: "Gemini"\napi_key: "k"\n')
    with pytest.raises(ValueError, match="LLM_Interface_Format") as exc:
        load_llm_config()
    # 报错应同时点名非法值与允许取值,便于排错。
    assert "Gemini" in str(exc.value)
    assert "OpenAI" in str(exc.value)
    assert "Anthropic" in str(exc.value)


def test_env_var_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_cfg(tmp_path, monkeypatch, 'api_key: "k"\n')  # yml 无该字段
    monkeypatch.setenv("LLM_INTERFACE_FORMAT", "OpenAI")
    assert load_llm_config().interface_format == "openai"


def test_factory_selects_openai_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_cfg(
        tmp_path,
        monkeypatch,
        'LLM_Interface_Format: "OpenAI"\napi_key: "k"\nmodel: "gpt-4o-mini"\ndev_stub: false\n',
    )
    assert isinstance(deps.get_provider(), OpenAIProvider)


def test_factory_defaults_to_anthropic_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_cfg(tmp_path, monkeypatch, 'api_key: "k"\nmodel: "claude-opus-4-8"\ndev_stub: false\n')
    assert isinstance(deps.get_provider(), AnthropicProvider)
