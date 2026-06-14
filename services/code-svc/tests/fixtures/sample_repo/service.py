"""编排:summarize_plan 串起取数、计算、格式化(虚构示例)。"""

from calculator import execution_rate
from formatting import format_summary
from repository import load_plan


def summarize_plan(plan_id):
    plan = load_plan(plan_id)
    rate = execution_rate(plan)
    return format_summary(plan, rate)
