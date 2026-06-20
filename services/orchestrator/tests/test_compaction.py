"""截断式压缩(§4.3,阶段 2)。"""

from __future__ import annotations

from llm import Message, Role, TextBlock, ToolResultBlock, ToolUseBlock
from orchestrator import TruncationCompactor


def _msgs(n: int) -> list[Message]:
    return [Message(role=Role.user, content=[TextBlock(str(i))]) for i in range(n)]


def _convo_with_tool_pairs(rounds: int) -> list[Message]:
    """[首条诉求] + 每轮(assistant tool_use, user tool_result)成对追加,模拟真实工具循环。"""
    msgs: list[Message] = [Message(role=Role.user, content=[TextBlock("原始诉求")])]
    for i in range(rounds):
        msgs.append(
            Message(role=Role.assistant, content=[ToolUseBlock(id=f"t{i}", name="echo", input={})])
        )
        msgs.append(Message(role=Role.user, content=[ToolResultBlock(f"t{i}", "ok")]))
    return msgs


def _orphan_tool_results(msgs: list[Message]) -> list[str]:
    """返回缺失配对 tool_use 的 tool_result 的 id(应为空 —— 否则真实 Anthropic API 会 400)。"""
    use_ids = {b.id for m in msgs for b in m.content if isinstance(b, ToolUseBlock)}
    return [
        b.tool_use_id
        for m in msgs
        for b in m.content
        if isinstance(b, ToolResultBlock) and b.tool_use_id not in use_ids
    ]


def test_truncation_keeps_first_and_recent() -> None:
    msgs = _msgs(50)
    out = TruncationCompactor(max_messages=10).compact(msgs)
    assert len(out) == 10
    assert out[0] is msgs[0]
    assert out[-1] is msgs[-1]


def test_no_truncation_under_limit() -> None:
    msgs = _msgs(5)
    out = TruncationCompactor(max_messages=10).compact(msgs)
    assert out is msgs


# ---- W1 不变式补强:截断不得产生孤儿 tool_result;输出不得超 max ---------------- #
def test_truncation_drops_orphan_tool_result() -> None:
    # 截断边界切在 tool_use(被裁)/ tool_result(保留)之间时,孤儿 tool_result 必须被修剪。
    msgs = _convo_with_tool_pairs(10)  # 1 + 20 = 21 条
    out = TruncationCompactor(max_messages=6).compact(msgs)
    assert _orphan_tool_results(out) == []  # 无孤儿(否则真实 API 400)
    assert out[0] is msgs[0]  # 首条诉求保留
    assert len(out) <= 6


def test_output_never_exceeds_max() -> None:
    msgs = _convo_with_tool_pairs(20)  # 41 条
    for m in (3, 5, 10, 40):
        out = TruncationCompactor(max_messages=m).compact(msgs)
        assert len(out) <= m
        assert _orphan_tool_results(out) == []


def test_max_one_keeps_only_first() -> None:
    # 退化配置 max=1:旧实现 messages[-0:] 返回整列(越压越多);现仅留首条。
    msgs = _msgs(5)
    out = TruncationCompactor(max_messages=1).compact(msgs)
    assert out == [msgs[0]]
