"""memory-svc 测试夹具。"""

from __future__ import annotations

import pytest

from memory_svc import MemoryService


@pytest.fixture
def memory() -> MemoryService:
    return MemoryService()
