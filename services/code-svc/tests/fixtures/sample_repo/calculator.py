"""计算逻辑(虚构示例)。execution_rate 与 variance 都调用 safe_div。"""

from mathutils import safe_div


def execution_rate(plan):
    return safe_div(plan.executed, plan.planned)


def variance(plan):
    return safe_div(plan.executed - plan.planned, plan.planned)
