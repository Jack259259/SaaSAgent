"""reflection-worker 服务包冒烟测试(阶段 0):仅验证包可导入、版本可读。"""

import reflection_worker


def test_reflection_worker_importable() -> None:
    assert reflection_worker.__version__ == "0.1.0"
