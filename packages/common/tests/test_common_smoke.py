"""common 包冒烟测试(阶段 0)。

仅验证:包可导入、版本可读、子模块存在;并用一个 async 用例确认
pytest-asyncio 的 asyncio_mode=auto 生效(后续阶段大量使用 async 工具/网关)。
"""

import common
from common import audit, auth_ctx, errors


def test_common_importable() -> None:
    assert common.__version__ == "0.1.0"
    # 三个空壳子模块应可导入(占位即可)
    assert auth_ctx is not None
    assert audit is not None
    assert errors is not None


async def test_asyncio_mode_enabled() -> None:
    # 无需显式 marker 即可运行 async 测试 => asyncio_mode=auto 生效
    assert True
