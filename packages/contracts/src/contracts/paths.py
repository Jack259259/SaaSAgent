"""定位仓库内的 contracts/ 目录与仓库根。

schema 文件位于仓库根 `contracts/`(语言中立的事实源,非本 Python 包的包内资源)。
本模块从 `__file__` 上溯寻找标记文件;支持 `CONTRACTS_DIR` 环境变量覆盖。
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path

# 用于识别仓库根的标记:contracts/toolspec/_schema.json 存在。
_MARKER = Path("contracts") / "toolspec" / "_schema.json"


@cache
def find_contracts_dir() -> Path:
    """返回仓库内 contracts/ 目录的绝对路径。"""
    env = os.environ.get("CONTRACTS_DIR")
    if env:
        p = Path(env).resolve()
        if not (p / "toolspec" / "_schema.json").is_file():
            raise RuntimeError(f"CONTRACTS_DIR={p} 下找不到 toolspec/_schema.json")
        return p
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / _MARKER).is_file():
            return parent / "contracts"
    raise RuntimeError("无法定位 contracts/ 目录;请设置环境变量 CONTRACTS_DIR 指向它")


@cache
def find_repo_root() -> Path:
    """返回仓库根目录(contracts/ 的父目录)。"""
    return find_contracts_dir().parent
