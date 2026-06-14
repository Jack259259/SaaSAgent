"""read_file:仓根内行段读取(红线 12)。

路径必须 realpath 落在索引仓根内(挡 ../ 穿越与符号链接逃逸);只回指定行段(有上限),
绝不把整文件交给调用方。
"""

from __future__ import annotations

from pathlib import Path

from .models import FileSlice

_DEFAULT_MAX_LINES = 200


class PathOutsideRepoError(Exception):
    """请求路径越出索引仓根。"""


def _within(target: Path, root: Path) -> bool:
    return target == root or root in target.parents


class FileReader:
    def __init__(self, repos_root: Path, *, max_lines: int = _DEFAULT_MAX_LINES) -> None:
        self._root = repos_root.resolve()
        self._max_lines = max_lines

    def read(self, rel_path: str, *, start_line: int = 1, end_line: int | None = None) -> FileSlice:
        target = (self._root / rel_path).resolve()
        if not _within(target, self._root):
            raise PathOutsideRepoError(rel_path)  # 红线 12:越界拒
        if not target.is_file():
            raise FileNotFoundError(rel_path)
        lines = target.read_text("utf-8", "replace").splitlines()
        start = max(1, start_line)
        end = end_line if end_line is not None else start + self._max_lines - 1
        end = min(end, len(lines), start + self._max_lines - 1)  # 上限封顶
        text = "\n".join(lines[start - 1 : end])
        return FileSlice(file=rel_path, start_line=start, end_line=max(start, end), text=text)
