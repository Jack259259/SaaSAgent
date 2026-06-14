"""数据模型(虚构示例)。"""

from dataclasses import dataclass


@dataclass
class Plan:
    plan_id: str
    planned: float
    executed: float

    def is_overspent(self):
        return self.executed > self.planned
