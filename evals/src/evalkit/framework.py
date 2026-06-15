"""评估框架(方案 §10.2):JSONL 用例加载 + 规则评分 + 阈值判定。

每个集合:`<set>/cases.jsonl`(输入 + 期望"性质",非标准答案)→ 逐例 scorer 判 ok →
通过率对比阈值。**严禁把标准答案喂回模型(§10 反模式)**:scorer 只断言安全/grounding 性质。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_EVALS_ROOT = Path(__file__).resolve().parents[2]  # evals/


@dataclass
class Case:
    id: str
    data: dict[str, Any]


@dataclass
class CaseResult:
    id: str
    ok: bool
    detail: str = ""


@dataclass
class SetResult:
    name: str
    threshold: float
    results: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def score(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def ok(self) -> bool:
        return self.total > 0 and self.score >= self.threshold

    def report(self) -> str:
        head = (
            f"[{self.name}] {self.passed}/{self.total} pass "
            f"(score={self.score:.3f} >= threshold={self.threshold:.2f}) "
            f"=> {'OK' if self.ok else 'FAIL'}"
        )
        fails = [f"  - FAIL {r.id}: {r.detail}" for r in self.results if not r.ok]
        return "\n".join([head, *fails])


def cases_path(set_name: str) -> Path:
    return _EVALS_ROOT / set_name / "cases.jsonl"


def load_jsonl(path: Path) -> list[Case]:
    cases: list[Case] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        obj = json.loads(line)
        cases.append(Case(id=str(obj["id"]), data=obj))
    return cases


CaseScorer = Callable[[Case], Awaitable[CaseResult]]


async def run_cases(
    name: str, cases: list[Case], scorer: CaseScorer, threshold: float
) -> SetResult:
    result = SetResult(name=name, threshold=threshold)
    for case in cases:
        try:
            result.results.append(await scorer(case))
        except Exception as exc:  # scorer 内崩溃即该例失败,记 detail
            result.results.append(CaseResult(case.id, ok=False, detail=f"scorer error: {exc!r}"))
    return result
