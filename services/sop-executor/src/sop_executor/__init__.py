"""sop-executor:SOP 确定性状态机 + 确认恢复 + postconditions 回查 + 回放(方案 §5.4)。

对外能力经 find_sop / run_sop 契约;本包提供 SopService / SopExecutor / sopcheck / replay。
"""

from __future__ import annotations

from .executor import RunAccessError, SopExecutor
from .httpcaller import HttpCaller
from .models import (
    Confirmation,
    RunReport,
    RunState,
    RunStatus,
    Sop,
    SopMatch,
    StepResult,
)
from .runstore import InMemoryRunStore, RunStore
from .service import SopService
from .steprunner import FakeUiRunner, PlaywrightUiRunner, UiStepRunner

__version__ = "0.1.0"

__all__ = [
    "Confirmation",
    "FakeUiRunner",
    "HttpCaller",
    "InMemoryRunStore",
    "PlaywrightUiRunner",
    "RunAccessError",
    "RunReport",
    "RunState",
    "RunStatus",
    "RunStore",
    "Sop",
    "SopExecutor",
    "SopMatch",
    "SopService",
    "StepResult",
    "UiStepRunner",
    "__version__",
]
