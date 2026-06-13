"""AnthropicProvider 未配置路径(不触网):缺 LLM_API_KEY → NotConfiguredError。"""

from __future__ import annotations

import pytest

from llm import AnthropicProvider, NotConfiguredError


async def test_complete_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    provider = AnthropicProvider()
    with pytest.raises(NotConfiguredError):
        await provider.complete(system="s", messages=[])


async def test_stream_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    provider = AnthropicProvider()
    with pytest.raises(NotConfiguredError):
        async for _ in provider.stream(system="s", messages=[]):
            pass


def test_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    provider = AnthropicProvider()
    assert provider._model == "claude-opus-4-8"
