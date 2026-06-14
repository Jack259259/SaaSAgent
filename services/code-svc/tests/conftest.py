"""code-svc 测试夹具:索引 fixtures/sample_repo 到临时 SQLite,返回 CodeService(Python 检索)。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from code_svc import CodeService, FileReader, PythonSearch, SymbolStore, index_repos

_SAMPLE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


@pytest.fixture
def repos_root() -> Path:
    return _SAMPLE_REPO


@pytest.fixture
def code_service(tmp_path: Path, repos_root: Path) -> Iterator[CodeService]:
    db = tmp_path / "symbols.db"
    index_repos(repos_root=repos_root, db_path=db)
    service = CodeService(
        repos_root=repos_root,
        store=SymbolStore(db),
        search=PythonSearch(repos_root, [repos_root]),
        reader=FileReader(repos_root),
    )
    yield service
    service.close()
