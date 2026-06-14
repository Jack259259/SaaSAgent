"""索引管线 CLI:`code-index --repos-root data/repos --db data/code-index/symbols.db`。

扫描 repos_root 下受支持文件(空目录幂等空跑)→ tree-sitter 抽取 → SQLite 符号库;
增量:按 (mtime, size) 跳过未变更;删除已消失文件的符号。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .languages import spec_for_path
from .parser import extract_symbols
from .store import SymbolStore

_DEFAULT_REPOS_ROOT = "data/repos"
_DEFAULT_DB = "data/code-index/symbols.db"


def index_repos(*, repos_root: Path, db_path: Path) -> dict[str, int]:
    store = SymbolStore(db_path)
    stats = {"files": 0, "indexed": 0, "skipped": 0, "removed": 0, "definitions": 0}
    present: set[str] = set()
    try:
        files = (
            sorted(p for p in repos_root.rglob("*") if p.is_file()) if repos_root.exists() else []
        )
        for path in files:
            spec = spec_for_path(path)
            if spec is None:
                continue  # 非支持语言,跳过
            rel = path.relative_to(repos_root).as_posix()
            present.add(rel)
            stats["files"] += 1
            st = path.stat()
            if store.file_meta(rel) == (st.st_mtime, st.st_size):
                stats["skipped"] += 1
                continue
            defs, refs, calls = extract_symbols(rel, path.read_bytes(), spec)
            store.replace_file(
                rel,
                language=spec.name,
                mtime=st.st_mtime,
                size=st.st_size,
                defs=defs,
                refs=refs,
                calls=calls,
            )
            stats["indexed"] += 1
            stats["definitions"] += len(defs)
        for gone in store.indexed_files() - present:
            store.remove_file(gone)
            stats["removed"] += 1
        store.commit()
    finally:
        store.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="code-index", description="代码符号索引(空目录幂等)")
    parser.add_argument("--repos-root", default=_DEFAULT_REPOS_ROOT, help="索引仓根目录")
    parser.add_argument("--db", default=_DEFAULT_DB, help="SQLite 符号库路径")
    args = parser.parse_args(argv)
    stats = index_repos(repos_root=Path(args.repos_root), db_path=Path(args.db))
    print(f"code-index repos={args.repos_root}: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
