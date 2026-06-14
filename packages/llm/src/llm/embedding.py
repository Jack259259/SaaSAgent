"""Embedding 网关(方案 §5.3 / §11.4)。

RAG 等的向量化经此接口,便于成本统计与离线/确定性测试;不直连厂商 SDK。
默认 HashingEmbedder 是确定性、零依赖的词法哈希向量器;生产可换神经向量(同接口)。
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

# 英文/数字按词,CJK 按单字(无空格分词)。
_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@runtime_checkable
class Embedder(Protocol):
    @property
    def dim(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """确定性词法哈希向量器:token → md5 桶 + tf 累加 + L2 归一。

    共享 token 越多 → cosine 越高。零依赖、离线、可复现;经 Embedder 网关暴露。
    """

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for token in _tokenize(text):
            bucket = int(hashlib.md5(token.encode("utf-8"), usedforsecurity=False).hexdigest(), 16)
            vec[bucket % self._dim] += 1.0
        norm = math.sqrt(sum(value * value for value in vec))
        if norm > 0.0:
            vec = [value / norm for value in vec]
        return vec

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]
