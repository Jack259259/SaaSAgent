"""code-svc:代码检索分析(tree-sitter 符号库 + repo map + Zoekt/ripgrep 词法检索,方案 §5.1)。

对外能力仅经 `ask_codebase` 契约(子 Agent 派发);本包提供 CodeService 与索引管线。
"""

from __future__ import annotations

from .indexer import index_repos
from .models import (
    CallEdge,
    Definition,
    FileSlice,
    Reference,
    RepoMap,
    RepoMapEntry,
    SearchHit,
)
from .reader import FileReader, PathOutsideRepoError
from .search import LexicalSearch, PythonSearch, RipgrepSearch, select_search
from .service import CodeService
from .store import SymbolStore

__version__ = "0.1.0"

__all__ = [
    "CallEdge",
    "CodeService",
    "Definition",
    "FileReader",
    "FileSlice",
    "LexicalSearch",
    "PathOutsideRepoError",
    "PythonSearch",
    "Reference",
    "RepoMap",
    "RepoMapEntry",
    "RipgrepSearch",
    "SearchHit",
    "SymbolStore",
    "__version__",
    "index_repos",
    "select_search",
]
