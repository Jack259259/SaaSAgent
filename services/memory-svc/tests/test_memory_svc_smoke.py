"""memory-svc 服务包冒烟测试(阶段 0):仅验证包可导入、版本可读。"""

import memory_svc


def test_memory_svc_importable() -> None:
    assert memory_svc.__version__ == "0.1.0"
