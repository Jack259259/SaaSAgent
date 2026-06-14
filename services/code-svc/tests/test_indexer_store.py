"""符号抽取 + find_definition/references/callers;空目录幂等 + 增量跳过。"""

from __future__ import annotations

from pathlib import Path

from code_svc import CodeService, index_repos


def test_find_definition(code_service: CodeService) -> None:
    defs = code_service.find_definition("safe_div")
    assert len(defs) == 1
    d = defs[0]
    assert d.file == "mathutils.py"
    assert d.kind == "function"
    assert d.start_line >= 1 and "safe_div" in d.snippet


def test_method_kind_detected(code_service: CodeService) -> None:
    defs = code_service.find_definition("is_overspent")
    assert defs and defs[0].kind == "method"  # 由所在 class 判定
    assert code_service.find_definition("Plan")[0].kind == "class"


def test_find_callers_of_safe_div(code_service: CodeService) -> None:
    callers = code_service.find_callers("safe_div")
    pairs = {(c.file, c.caller) for c in callers}
    assert ("calculator.py", "execution_rate") in pairs
    assert ("calculator.py", "variance") in pairs
    for c in callers:
        assert c.line >= 1 and "safe_div" in c.snippet  # 证据带行号 + snippet


def test_find_references_spans_files(code_service: CodeService) -> None:
    files = {r.file for r in code_service.find_references("execution_rate")}
    assert "calculator.py" in files  # 定义处
    assert "service.py" in files  # 使用处


def test_empty_dir_index_idempotent(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    db = tmp_path / "e.db"
    first = index_repos(repos_root=empty, db_path=db)
    assert first["files"] == 0 and first["indexed"] == 0
    assert index_repos(repos_root=empty, db_path=db) == first  # 幂等空跑


def test_incremental_skip_unchanged(tmp_path: Path, repos_root: Path) -> None:
    db = tmp_path / "s.db"
    first = index_repos(repos_root=repos_root, db_path=db)
    assert first["indexed"] == 7 and first["skipped"] == 0
    second = index_repos(repos_root=repos_root, db_path=db)
    assert second["indexed"] == 0 and second["skipped"] == 7
