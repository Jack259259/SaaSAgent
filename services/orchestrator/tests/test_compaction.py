"""截断式压缩(§4.3,阶段 2)。"""

from __future__ import annotations

from llm import Message, Role, TextBlock
from orchestrator import TruncationCompactor


def _msgs(n: int) -> list[Message]:
    return [Message(role=Role.user, content=[TextBlock(str(i))]) for i in range(n)]


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
