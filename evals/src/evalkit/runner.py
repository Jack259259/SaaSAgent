"""评估 runner(§10.2):`make eval E=<set>` → `python -m evalkit <set>`。

阈值见 evals/README.md(README 为人读事实源,此处执行口径须与之一致);低于阈值 → 非零退出。
sop-replay 仍由 `sop_executor.replay` 执行(Makefile 路由),不在此 runner 内。
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any

from .framework import SetResult
from .sets import code_qa, e2e, nl2sql, rag_qa

THRESHOLDS: dict[str, float] = {
    "nl2sql": 0.95,
    "rag-qa": 0.9,
    "code-qa": 0.9,
    "e2e": 1.0,
}

_RUNNERS: dict[str, Callable[[float], Coroutine[Any, Any, SetResult]]] = {
    "nl2sql": nl2sql.run,
    "rag-qa": rag_qa.run,
    "code-qa": code_qa.run,
    "e2e": e2e.run,
}

_SOP_REPLAY = "sop-replay"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m evalkit <nl2sql|rag-qa|code-qa|e2e>")
        return 1
    name = args[0]
    if name == _SOP_REPLAY:
        print("sop-replay 由 sop_executor.replay 执行:make eval E=sop-replay")
        return 1
    runner = _RUNNERS.get(name)
    if runner is None:
        print(f"unknown eval set: {name}")
        return 1
    result = asyncio.run(runner(THRESHOLDS[name]))
    print(result.report())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
