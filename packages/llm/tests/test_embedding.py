"""HashingEmbedder:确定性、维度、词法相似度单调性。"""

from __future__ import annotations

import math
from collections.abc import Sequence

from llm import HashingEmbedder


def _cos(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # 已 L2 归一,点积即 cosine


async def test_deterministic_and_dim() -> None:
    emb = HashingEmbedder(dim=128)
    v1 = await emb.embed(["资金计划执行率口径"])
    v2 = await emb.embed(["资金计划执行率口径"])
    assert v1 == v2  # 确定性
    assert len(v1[0]) == 128


async def test_similarity_monotonic() -> None:
    emb = HashingEmbedder()
    (anchor,) = await emb.embed(["资金计划执行率口径"])
    (related,) = await emb.embed(["执行率口径说明"])
    (unrelated,) = await emb.embed(["今天天气晴朗适合出游"])
    assert _cos(anchor, related) > _cos(anchor, unrelated)


async def test_normalized() -> None:
    emb = HashingEmbedder()
    (vec,) = await emb.embed(["归一化检查"])
    assert math.isclose(math.sqrt(sum(v * v for v in vec)), 1.0, rel_tol=1e-9)
