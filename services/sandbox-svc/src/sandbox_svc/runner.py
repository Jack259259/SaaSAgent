"""受限沙箱运行器(红线 11)。

SubprocessRunner:开发 / CI 用,独立子进程 + 注入式护栏(_harness.py)+ 墙钟超时 + POSIX rlimit。
ContainerRunner:生产用(gVisor / 容器),本阶段仅接口 + TODO,见 docs/integration/sandbox.md。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

_HARNESS = Path(__file__).with_name("_harness.py")

# 仅透传子进程启动所必需的环境变量;**绝不**透传 DB_DSN / LLM_API_KEY / 代理等(无库连接、无网络)。
_ENV_KEEP = {
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "SYSTEMDRIVE",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "NUMBER_OF_PROCESSORS",
    "LD_LIBRARY_PATH",
}


@dataclass(frozen=True)
class SandboxInput:
    """只读挂载到沙箱的输入文件(对应一个工作区句柄)。"""

    name: str
    data: bytes


@dataclass
class SandboxRequest:
    code: str
    inputs: list[SandboxInput] = field(default_factory=list)
    timeout_s: float = 10.0
    max_output_bytes: int = 64 * 1024
    mem_headroom_bytes: int = 256 * 1024 * 1024


@dataclass
class SandboxResult:
    ok: bool
    stdout: str
    stderr: str
    artifacts: dict[str, bytes]
    exit_code: int | None
    timed_out: bool


class SandboxRunner(Protocol):
    def run(self, request: SandboxRequest) -> SandboxResult: ...


def _truncate(text: str | bytes | None, limit: int) -> str:
    if not text:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(truncated)"


def _build_env(request: SandboxRequest, input_rel: list[str]) -> dict[str, str]:
    keep_upper = {name.upper() for name in _ENV_KEEP}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep_upper}
    env["MPLBACKEND"] = "Agg"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["SANDBOX_INPUTS"] = json.dumps(input_rel)
    env["SANDBOX_CPU_S"] = str(int(request.timeout_s) + 1)
    env["SANDBOX_MEM_HEADROOM"] = str(request.mem_headroom_bytes)
    return env


class SubprocessRunner:
    """子进程沙箱(注入式 best-effort);真正强隔离见 ContainerRunner。"""

    def run(self, request: SandboxRequest) -> SandboxResult:
        with tempfile.TemporaryDirectory(prefix="sbx_") as tmp:
            sandbox_dir = Path(tmp)
            (sandbox_dir / "user_code.py").write_text(request.code, encoding="utf-8")
            inputs_dir = sandbox_dir / "inputs"
            inputs_dir.mkdir()
            artifacts_dir = sandbox_dir / "artifacts"
            artifacts_dir.mkdir()

            input_rel: list[str] = []
            for inp in request.inputs:
                (inputs_dir / inp.name).write_bytes(inp.data)
                input_rel.append(f"inputs/{inp.name}")

            cmd = [sys.executable, "-I", str(_HARNESS), str(sandbox_dir)]
            env = _build_env(request, input_rel)
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(sandbox_dir),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=request.timeout_s,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                # subprocess.run 在超时时已 kill 子进程
                return SandboxResult(
                    ok=False,
                    stdout=_truncate(exc.stdout, request.max_output_bytes),
                    stderr="sandbox: wall-clock timeout",
                    artifacts={},
                    exit_code=None,
                    timed_out=True,
                )

            artifacts = {
                item.name: item.read_bytes()
                for item in sorted(artifacts_dir.iterdir())
                if item.is_file()
            }
            return SandboxResult(
                ok=proc.returncode == 0,
                stdout=_truncate(proc.stdout, request.max_output_bytes),
                stderr=_truncate(proc.stderr, request.max_output_bytes),
                artifacts=artifacts,
                exit_code=proc.returncode,
                timed_out=False,
            )


class ContainerRunner:
    """生产沙箱(gVisor / 容器)。本阶段不实现——见 docs/integration/sandbox.md 的生产化要求。"""

    def run(self, request: SandboxRequest) -> SandboxResult:
        raise NotImplementedError(
            "ContainerRunner 待生产化实现(gVisor/容器 + 网络命名空间 + 只读 rootfs + seccomp);"
            "见 docs/integration/sandbox.md"
        )
