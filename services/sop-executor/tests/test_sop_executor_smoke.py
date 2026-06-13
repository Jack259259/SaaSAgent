"""sop-executor 服务包冒烟测试(阶段 0):仅验证包可导入、版本可读。"""

import sop_executor


def test_sop_executor_importable() -> None:
    assert sop_executor.__version__ == "0.1.0"
