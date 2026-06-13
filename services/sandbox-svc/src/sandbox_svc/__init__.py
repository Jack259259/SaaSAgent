"""sandbox-svc —— run_analysis 受限沙箱(CLAUDE.md 红线 11 / 方案 §5.5)。"""

from __future__ import annotations

from .runner import (
    ContainerRunner,
    SandboxInput,
    SandboxRequest,
    SandboxResult,
    SandboxRunner,
    SubprocessRunner,
)

__version__ = "0.1.0"

__all__ = [
    "ContainerRunner",
    "SandboxInput",
    "SandboxRequest",
    "SandboxResult",
    "SandboxRunner",
    "SubprocessRunner",
]
