"""evalkit 框架单测:JSONL 加载、通过率/阈值判定、RuleJudge、LlmJudge(MockProvider)。"""

from __future__ import annotations

from pathlib import Path

from evalkit import Case, CaseResult, LlmJudge, RuleJudge, load_jsonl, run_cases
from evalkit.runner import THRESHOLDS
from llm import MockProvider, ScriptedTurn


def test_load_jsonl_skips_comments_and_blanks(tmp_path: Path) -> None:
    p = tmp_path / "c.jsonl"
    p.write_text('# 注释\n\n{"id":"a","x":1}\n{"id":"b","x":2}\n', encoding="utf-8")
    cases = load_jsonl(p)
    assert [c.id for c in cases] == ["a", "b"]
    assert cases[0].data["x"] == 1


async def test_run_cases_threshold() -> None:
    cases = [Case("a", {}), Case("b", {}), Case("c", {})]

    async def scorer(case: Case) -> CaseResult:
        return CaseResult(case.id, case.id != "c")  # c 失败

    res = await run_cases("demo", cases, scorer, threshold=0.6)
    assert res.passed == 2 and res.total == 3
    assert res.ok  # 0.667 >= 0.6

    strict = await run_cases("demo", cases, scorer, threshold=0.9)
    assert not strict.ok
    assert "FAIL c" in strict.report()


async def test_run_cases_scorer_error_is_failure() -> None:
    async def boom(case: Case) -> CaseResult:
        raise RuntimeError("x")

    res = await run_cases("d", [Case("a", {})], boom, 1.0)
    assert not res.ok and "scorer error" in res.results[0].detail


async def test_rule_judge() -> None:
    judge = RuleJudge()
    ok, _ = await judge.grade(answer="含 公开 与 内部", must_include=["公开", "内部"])
    assert ok
    bad, detail = await judge.grade(answer="只有公开", must_include=["内部"])
    assert not bad and "内部" in detail


async def test_llm_judge_with_mock_provider() -> None:
    provider = MockProvider([ScriptedTurn(text="PASS")])
    ok, detail = await LlmJudge(provider).grade(answer="x", must_include=["a"])
    assert ok and "PASS" in detail


def test_thresholds_cover_four_sets() -> None:
    assert set(THRESHOLDS) == {"nl2sql", "rag-qa", "code-qa", "e2e"}
    assert THRESHOLDS["e2e"] == 1.0
