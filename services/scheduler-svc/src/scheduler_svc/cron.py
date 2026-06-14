"""下次触发时间(best-effort)。支持 `*/N * * * *`(每 N 分钟)、`@hourly`、`@daily`,缺省每小时。

完整 cron 解析非本阶段重点;轮询调度据 next_run_at 触发,精度足够演示与测试。
"""

from __future__ import annotations

import re

_EVERY_N_MIN = re.compile(r"^\*/(\d+)\s")
_MINUTE = 60.0
_HOUR = 3600.0
_DAY = 86400.0


def next_run(cron: str, after: float) -> float:
    spec = cron.strip()
    if spec == "@hourly":
        return after + _HOUR
    if spec == "@daily":
        return after + _DAY
    match = _EVERY_N_MIN.match(spec)
    if match:
        return after + int(match.group(1)) * _MINUTE
    return after + _HOUR  # 缺省每小时
