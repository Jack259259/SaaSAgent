"""沙箱子进程引导(仅标准库)。红线 11:装配隔离护栏后 exec 模型生成的分析代码。

护栏(注入式,best-effort;真正强隔离由生产 ContainerRunner 承担):
- import 白名单(meta_path):仅标准库 + pandas/numpy/matplotlib,且剔除逃逸 stdlib(subprocess 等);
- 网络禁用:socket 创建即抛错;
- 路径隔离:open 读限 sandbox + python 前缀,写限 sandbox;
- 资源限额(仅 POSIX):RLIMIT_CPU + RLIMIT_AS(在预热重库后施加)。

重库经 importlib 动态导入,使受检代码不静态依赖 pandas/matplotlib 类型。
"""

from __future__ import annotations

import builtins
import contextlib
import importlib
import json
import os
import sys
from typing import Any, NoReturn

_EXTRA_ALLOWED = {"numpy", "pandas", "matplotlib", "mpl_toolkits"}
_DENY_STDLIB = {"subprocess", "multiprocessing", "ctypes", "socketserver"}


def _warmup(sandbox_dir: str) -> None:
    """装护栏前预热重库与 matplotlib 字体缓存(savefig 扫描系统字体,须早于 open 护栏)。"""
    with contextlib.suppress(Exception):  # 库缺失/预热失败不致命,用户代码会自行报错
        importlib.import_module("numpy")
        importlib.import_module("pandas")
        plt = importlib.import_module("matplotlib.pyplot")
        figure = plt.figure()
        plt.plot([0, 1], [0, 1])
        plt.savefig(os.path.join(sandbox_dir, ".warmup.png"))
        plt.close(figure)


class _ImportGuard:
    """sys.meta_path 守卫:白名单外的顶层模块导入直接拒绝。"""

    def __init__(self, allowed: set[str]) -> None:
        self._allowed = allowed

    def find_spec(self, fullname: str, path: object = None, target: object = None) -> None:
        top = fullname.split(".")[0]
        if top in self._allowed:
            return None  # 放行,交还给真正的 finder
        raise ImportError(f"sandbox: import of '{top}' is not allowed")


def _install_import_guard() -> None:
    allowed = (set(sys.stdlib_module_names) | _EXTRA_ALLOWED) - _DENY_STDLIB
    sys.meta_path.insert(0, _ImportGuard(allowed))


def _install_network_block() -> None:
    import socket

    def _blocked(*args: object, **kwargs: object) -> NoReturn:
        raise OSError("sandbox: network is disabled")

    socket.socket = _blocked  # type: ignore[misc, assignment]
    socket.create_connection = _blocked
    if hasattr(socket, "create_server"):
        socket.create_server = _blocked


def _under(path: str, root: str) -> bool:
    abs_path = os.path.normcase(os.path.abspath(path))
    abs_root = os.path.normcase(os.path.abspath(root))
    return abs_path == abs_root or abs_path.startswith(abs_root + os.sep)


def _install_open_guard(sandbox_dir: str, read_roots: list[str]) -> None:
    real_open = builtins.open

    def guarded(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        target = file
        if isinstance(target, int):  # 文件描述符:放行
            return real_open(file, mode, *args, **kwargs)
        if isinstance(target, bytes):
            target = os.fsdecode(target)
        if hasattr(target, "__fspath__"):
            target = os.fspath(target)
        path = str(target)
        if any(c in mode for c in "wax+"):
            if not _under(path, sandbox_dir):
                raise PermissionError(f"sandbox: write outside sandbox denied: {path}")
        elif not any(_under(path, root) for root in read_roots):
            raise PermissionError(f"sandbox: read outside sandbox denied: {path}")
        return real_open(file, mode, *args, **kwargs)

    builtins.open = guarded


def _limit_resources(cpu_seconds: int, mem_headroom: int) -> None:
    # CPU/内存 rlimit 仅 POSIX(Windows 无 resource,本机由墙钟超时兜底)。
    # 整体置于 sys.platform 守卫内:mypy 在 win32 下豁免该分支(不报 unreachable)。
    if sys.platform != "win32":
        import resource

        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        # 内存:预热重库之后,按"当前虚拟内存 + headroom"设上限(对 numpy 虚拟预留友好)。
        try:
            with open("/proc/self/statm", encoding="ascii") as statm:
                pages = int(statm.read().split()[0])
            limit = pages * os.sysconf("SC_PAGE_SIZE") + mem_headroom
        except (OSError, ValueError, IndexError):
            limit = 1024 * 1024 * 1024  # 非 Linux POSIX 兜底
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def main() -> int:
    sandbox_dir = sys.argv[1]
    with open(os.path.join(sandbox_dir, "user_code.py"), encoding="utf-8") as code_file:
        code = code_file.read()  # 护栏未装,允许读取
    inputs = json.loads(os.environ.get("SANDBOX_INPUTS", "[]"))
    cpu_seconds = int(os.environ.get("SANDBOX_CPU_S", "10"))
    mem_headroom = int(os.environ.get("SANDBOX_MEM_HEADROOM", str(256 * 1024 * 1024)))

    _warmup(sandbox_dir)  # 预热重库与字体缓存(早于限额与护栏)
    _limit_resources(cpu_seconds, mem_headroom)
    _install_import_guard()
    _install_network_block()
    read_roots = [sandbox_dir, sys.prefix, sys.base_prefix, sys.exec_prefix]
    _install_open_guard(sandbox_dir, read_roots)

    os.chdir(sandbox_dir)
    sandbox_globals: dict[str, Any] = {
        "__name__": "__main__",
        "__builtins__": builtins,
        "INPUTS": inputs,
        "OUTPUT_DIR": "artifacts",
    }
    exec(compile(code, "user_code.py", "exec"), sandbox_globals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
