"""agent-gateway 服务包冒烟测试(阶段 0):仅验证包可导入、版本可读。"""

import agent_gateway


def test_agent_gateway_importable() -> None:
    assert agent_gateway.__version__ == "0.1.0"
