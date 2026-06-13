"""会话级预热 matplotlib 字体缓存。

沙箱子进程与测试进程共享同一缓存目录(USERPROFILE/HOME 下的 ~/.matplotlib),
预先在测试进程构建一次字体缓存,使后续沙箱子进程的预热快速完成,负例在其 timeout 内稳定通过。
"""

from __future__ import annotations

import contextlib
import importlib
import os
import tempfile
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _warm_font_cache() -> Iterator[None]:
    with contextlib.suppress(Exception):  # 预热失败不应阻断测试,子进程会自行重建
        matplotlib = importlib.import_module("matplotlib")
        matplotlib.use("Agg")
        plt = importlib.import_module("matplotlib.pyplot")
        figure = plt.figure()
        plt.plot([0, 1], [0, 1])
        with tempfile.TemporaryDirectory() as warm_dir:
            plt.savefig(os.path.join(warm_dir, "warm.png"))
        plt.close(figure)
    yield
