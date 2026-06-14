"""词法检索:PythonSearch 与 RipgrepSearch 结构一致;read_file 越界拒(红线 12)。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from code_svc import FileReader, PathOutsideRepoError, PythonSearch, RipgrepSearch


def test_python_search_finds_symbol(repos_root: Path) -> None:
    hits = PythonSearch(repos_root, [repos_root]).search("safe_div")
    files = {h.file for h in hits}
    assert "mathutils.py" in files and "calculator.py" in files
    for h in hits:
        assert h.line >= 1 and "safe_div" in h.snippet


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg 不在 PATH")
def test_ripgrep_fallback_structure_consistent(repos_root: Path) -> None:
    rg_hits = RipgrepSearch(repos_root, [repos_root]).search("safe_div")
    py_files = {(h.file, h.line) for h in PythonSearch(repos_root, [repos_root]).search("safe_div")}
    rg_files = {(h.file, h.line) for h in rg_hits}
    assert rg_hits and rg_files == py_files  # 回退后结果与结构一致
    for h in rg_hits:
        assert h.file and h.line >= 1 and h.snippet


def test_read_file_returns_range(repos_root: Path) -> None:
    sl = FileReader(repos_root).read("mathutils.py", start_line=1, end_line=3)
    assert sl.file == "mathutils.py" and sl.start_line == 1 and sl.end_line <= 3


def test_read_file_outside_repo_rejected(repos_root: Path) -> None:
    with pytest.raises(PathOutsideRepoError):
        FileReader(repos_root).read("../../../../../../etc/passwd")
