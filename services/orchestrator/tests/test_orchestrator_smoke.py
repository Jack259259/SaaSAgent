"""orchestrator 服务包冒烟测试(阶段 0):仅验证包可导入、版本可读。"""

import orchestrator


def test_orchestrator_importable() -> None:
    assert orchestrator.__version__ == "0.1.0"
