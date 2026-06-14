"""CodeService:聚合符号库 / 词法检索 / repo map / 行段读取(方案 §5.1)。

子 Agent 的 6 个工具都经此服务;repos_root = 索引仓根(默认 data/repos)。
"""

from __future__ import annotations

from pathlib import Path

from .models import CallEdge, Definition, FileSlice, Reference, RepoMap, SearchHit
from .reader import FileReader
from .repomap import build_repo_map
from .search import LexicalSearch, select_search
from .store import SymbolStore

_DEFAULT_REPOS_ROOT = Path("data/repos")
_DEFAULT_DB = Path("data/code-index/symbols.db")
_DEFAULT_TOKEN_BUDGET = 1000


class CodeService:
    def __init__(
        self,
        *,
        repos_root: Path,
        store: SymbolStore,
        search: LexicalSearch,
        reader: FileReader,
        repo_map_token_budget: int = _DEFAULT_TOKEN_BUDGET,
    ) -> None:
        self._repos_root = repos_root
        self._store = store
        self._search = search
        self._reader = reader
        self._token_budget = repo_map_token_budget

    @classmethod
    def open(
        cls,
        *,
        repos_root: Path = _DEFAULT_REPOS_ROOT,
        db_path: Path = _DEFAULT_DB,
        zoekt_url: str | None = None,
    ) -> CodeService:
        roots = [repos_root] if repos_root.exists() else []
        return cls(
            repos_root=repos_root,
            store=SymbolStore(db_path),
            search=select_search(repos_root, roots, zoekt_url=zoekt_url),
            reader=FileReader(repos_root),
        )

    def search_code(self, pattern: str, *, limit: int = 50) -> list[SearchHit]:
        return self._search.search(pattern, limit=limit)

    def find_definition(self, name: str) -> list[Definition]:
        return self._store.find_definition(name)

    def find_references(self, name: str) -> list[Reference]:
        return self._store.find_references(name)

    def find_callers(self, name: str) -> list[CallEdge]:
        return self._store.find_callers(name)

    def read_file(
        self, path: str, *, start_line: int = 1, end_line: int | None = None
    ) -> FileSlice:
        return self._reader.read(path, start_line=start_line, end_line=end_line)

    def get_repo_map(self, *, token_budget: int | None = None) -> RepoMap:
        return build_repo_map(self._store, token_budget=token_budget or self._token_budget)

    def close(self) -> None:
        self._store.close()
