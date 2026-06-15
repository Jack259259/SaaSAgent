"""evalkit —— 评估套件(方案 §10;CLAUDE.md §7/§10)。

统一 runner + 规则评分 + 5 金标集(nl2sql / rag-qa / code-qa / sop-replay / e2e),
全部基于 fixture/stub,不连真实数据。阈值见 evals/README.md。
"""

from __future__ import annotations

from .framework import Case, CaseResult, SetResult, cases_path, load_jsonl, run_cases
from .judge import Judge, LlmJudge, RuleJudge

__version__ = "0.1.0"

__all__ = [
    "Case",
    "CaseResult",
    "Judge",
    "LlmJudge",
    "RuleJudge",
    "SetResult",
    "cases_path",
    "load_jsonl",
    "run_cases",
]
