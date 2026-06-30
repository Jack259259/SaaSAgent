"""OpenAIProvider 不触网单测:未配置路径 + 请求构造 / 响应解析的格式转换正确性。

真实调用走 MockProvider / 手工实测脚本;此处只验证适配器的纯函数部分(无 SDK、无网络)。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from llm import NotConfiguredError, OpenAIProvider
from llm.types import (
    Message,
    Role,
    TextBlock,
    ToolDef,
    ToolResultBlock,
    ToolUseBlock,
)


async def test_complete_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    provider = OpenAIProvider()
    with pytest.raises(NotConfiguredError):
        await provider.complete(system="s", messages=[])


async def test_stream_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    provider = OpenAIProvider()
    with pytest.raises(NotConfiguredError):
        async for _ in provider.stream(system="s", messages=[]):
            pass


def test_model_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    provider = OpenAIProvider()
    assert provider._model == "gpt-4o-mini"


def test_system_goes_into_messages_array() -> None:
    """OpenAI:system 放进 messages 首条(Anthropic 是独立参数)。"""
    msgs = OpenAIProvider._api_messages_with_system(
        "你是助手", [Message(role=Role.user, content=[TextBlock("你好")])]
    )
    assert msgs[0] == {"role": "system", "content": "你是助手"}
    assert msgs[1] == {"role": "user", "content": "你好"}


def test_assistant_tool_use_maps_to_tool_calls() -> None:
    msg = Message(
        role=Role.assistant,
        content=[
            TextBlock("我来查一下"),
            ToolUseBlock(id="call_1", name="search", input={"q": "余额", "n": 3}),
        ],
    )
    out = OpenAIProvider._to_api_messages([msg])
    assert len(out) == 1
    assert out[0]["role"] == "assistant"
    assert out[0]["content"] == "我来查一下"
    tool_calls = out[0]["tool_calls"]
    assert tool_calls[0]["id"] == "call_1"
    assert tool_calls[0]["type"] == "function"
    assert tool_calls[0]["function"]["name"] == "search"
    # arguments 是 JSON 字符串(非 dict),且保留非 ASCII。
    assert tool_calls[0]["function"]["arguments"] == '{"q": "余额", "n": 3}'


def test_assistant_without_text_has_null_content() -> None:
    msg = Message(
        role=Role.assistant,
        content=[ToolUseBlock(id="c1", name="t", input={})],
    )
    out = OpenAIProvider._to_api_messages([msg])
    assert out[0]["content"] is None
    assert "tool_calls" in out[0]


def test_tool_results_become_separate_tool_messages() -> None:
    """Anthropic 把多个 tool_result 并到一条 user;OpenAI 各拆为独立 role:"tool" 消息。"""
    msg = Message(
        role=Role.user,
        content=[
            ToolResultBlock(tool_use_id="call_1", content="结果A"),
            ToolResultBlock(tool_use_id="call_2", content="结果B", is_error=True),
        ],
    )
    out = OpenAIProvider._to_api_messages([msg])
    assert out == [
        {"role": "tool", "tool_call_id": "call_1", "content": "结果A"},
        {"role": "tool", "tool_call_id": "call_2", "content": "结果B"},
    ]


def test_user_text_message() -> None:
    out = OpenAIProvider._to_api_messages([Message(role=Role.user, content=[TextBlock("一句话")])])
    assert out == [{"role": "user", "content": "一句话"}]


def test_to_api_tools_uses_function_parameters() -> None:
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    tools = [ToolDef(name="search", description="搜索", input_schema=schema)]
    out = OpenAIProvider._to_api_tools(tools)
    assert out == [
        {
            "type": "function",
            "function": {"name": "search", "description": "搜索", "parameters": schema},
        }
    ]


def test_parse_message_text_and_tool_calls() -> None:
    message = SimpleNamespace(
        content="好的",
        tool_calls=[
            SimpleNamespace(
                id="call_9",
                function=SimpleNamespace(name="query", arguments='{"x": 1}'),
            )
        ],
    )
    text, tool_calls, raw = OpenAIProvider._parse_message(message)
    assert text == "好的"
    assert tool_calls == [ToolUseBlock(id="call_9", name="query", input={"x": 1})]
    assert len(raw) == 2  # TextBlock + ToolUseBlock


def test_parse_message_no_tool_calls() -> None:
    message = SimpleNamespace(content="纯文本", tool_calls=None)
    text, tool_calls, _raw = OpenAIProvider._parse_message(message)
    assert text == "纯文本"
    assert tool_calls == []


def test_parse_tool_args_handles_bad_json() -> None:
    assert OpenAIProvider._parse_tool_args("") == {}
    assert OpenAIProvider._parse_tool_args("not json") == {}
    assert OpenAIProvider._parse_tool_args("[1, 2]") == {}  # 非 dict 顶层 → {}
    assert OpenAIProvider._parse_tool_args('{"a": 1}') == {"a": 1}


def test_usage_maps_openai_field_names() -> None:
    usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7)
    out = OpenAIProvider._usage(usage)
    assert out.input_tokens == 11
    assert out.output_tokens == 7


def test_usage_handles_missing() -> None:
    out = OpenAIProvider._usage(None)
    assert out.input_tokens == 0
    assert out.output_tokens == 0
