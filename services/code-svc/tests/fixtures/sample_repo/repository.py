"""取数仓储层(虚构示例)。"""

from models import Plan


def load_plan(plan_id):
    return Plan(plan_id=plan_id, planned=100.0, executed=60.0)
