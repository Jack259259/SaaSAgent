"""词法检索:三后端结构一致(SearchHit)。

select_search:ZOEKT_URL 可达 → ZoektSearch;否则 rg 在 → RipgrepSearch;再否则 → PythonSearch
(纯 Python 兜底,保证测试 hermetic)。**所有后端只在索引仓根内检索**(红线 12:受控、限仓)。

# 预留:语义向量检索接口(方案 §5.1 暂不上;概念式查询命中率持续偏低再评估)。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

import httpx

from .models import SearchHit

_MAX_FILE_BYTES = 1_000_000


class LexicalSearch(Protocol):
    def search(self, pattern: str, *, limit: int = 50) -> list[SearchHit]: ...


def _rel(path: Path, repos_root: Path) -> str:
    try:
        return path.resolve().relative_to(repos_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


class RipgrepSearch:
    """zoekt 未运行时的回退:rg 子进程,检索路径限定在仓根内。"""

    def __init__(self, repos_root: Path, roots: list[Path], *, rg_path: str | None = None) -> None:
        self._repos_root = repos_root
        self._roots = roots
        self._rg = rg_path or shutil.which("rg") or "rg"

    def search(self, pattern: str, *, limit: int = 50) -> list[SearchHit]:
        if not self._roots:
            return []
        cmd = [self._rg, "--json", "-n", "--no-heading", "-e", pattern, *map(str, self._roots)]
        # rg --json 输出恒为 UTF-8;显式 UTF-8 解码,勿用系统区域编码(Windows 为 GBK 会崩)。
        proc = subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=20, check=False
        )
        hits: list[SearchHit] = []
        for raw in proc.stdout.splitlines():
            if not raw:
                continue
            event = json.loads(raw)
            if event.get("type") != "match":
                continue
            data = event["data"]
            hits.append(
                SearchHit(
                    file=_rel(Path(data["path"]["text"]), self._repos_root),
                    line=int(data["line_number"]),
                    snippet=str(data["lines"]["text"]).rstrip("\n")[:200],
                )
            )
            if len(hits) >= limit:
                break
        return hits


class PythonSearch:
    """纯 Python 兜底(无 rg / 无 zoekt 时):逐文件逐行正则,限仓根内。"""

    def __init__(self, repos_root: Path, roots: list[Path]) -> None:
        self._repos_root = repos_root
        self._roots = roots

    def search(self, pattern: str, *, limit: int = 50) -> list[SearchHit]:
        regex = re.compile(pattern)
        hits: list[SearchHit] = []
        for root in self._roots:
            for path in sorted(p for p in root.rglob("*") if p.is_file()):
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                try:
                    text = path.read_text("utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        hits.append(
                            SearchHit(
                                file=_rel(path, self._repos_root),
                                line=lineno,
                                snippet=line.rstrip()[:200],
                            )
                        )
                        if len(hits) >= limit:
                            return hits
        return hits


class ZoektSearch:
    """Zoekt webserver JSON API(生产词法索引;docker compose 默认停用)。"""

    def __init__(self, base_url: str, repos_root: Path, *, timeout_s: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._repos_root = repos_root
        self._timeout = timeout_s

    def search(self, pattern: str, *, limit: int = 50) -> list[SearchHit]:
        resp = httpx.post(
            f"{self._base_url}/api/search",
            json={"Q": pattern, "Opts": {"Whole": False, "ShardMaxMatchCount": limit}},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        result = resp.json()
        hits: list[SearchHit] = []
        for file_match in result.get("Result", {}).get("Files", []) or []:
            for line_match in file_match.get("LineMatches", []) or []:
                hits.append(
                    SearchHit(
                        file=str(file_match.get("FileName", "")),
                        line=int(line_match.get("LineNumber", 0)),
                        snippet=str(line_match.get("Line", ""))[:200],
                    )
                )
                if len(hits) >= limit:
                    return hits
        return hits


def _zoekt_reachable(url: str) -> bool:
    try:
        httpx.get(f"{url.rstrip('/')}/", timeout=1.0)
    except (httpx.HTTPError, OSError):
        return False
    return True


def select_search(
    repos_root: Path, roots: list[Path], *, zoekt_url: str | None = None
) -> LexicalSearch:
    if zoekt_url and _zoekt_reachable(zoekt_url):
        return ZoektSearch(zoekt_url, repos_root)
    if shutil.which("rg"):
        return RipgrepSearch(repos_root, roots)
    return PythonSearch(repos_root, roots)
