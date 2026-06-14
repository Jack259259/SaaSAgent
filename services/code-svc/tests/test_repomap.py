"""repo map:度中心性排序 + token 预算截断。"""

from __future__ import annotations

from code_svc import CodeService


def test_repo_map_sorted_and_includes_hot_symbol(code_service: CodeService) -> None:
    rm = code_service.get_repo_map(token_budget=2000)
    names = [e.name for e in rm.entries]
    assert "safe_div" in names  # 被多处调用/引用,必入图
    scores = [e.score for e in rm.entries]
    assert scores == sorted(scores, reverse=True)  # 降序
    assert rm.total_symbols >= 7
    assert not rm.truncated


def test_repo_map_token_budget_truncates(code_service: CodeService) -> None:
    small = code_service.get_repo_map(token_budget=6)
    assert small.truncated
    assert 0 < len(small.entries) < small.total_symbols
