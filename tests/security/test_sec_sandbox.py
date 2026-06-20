"""红线 11:run_analysis 受限沙箱隔离安全负例(中心红线索引 + 边界补缺)。

穷举用例(断网/越界读/墙钟超时/import 白名单外/内存限额 POSIX/正例 CSV→PNG)为**单一事实源**,
见 `services/sandbox-svc/tests/test_subprocess_runner.py`。本文件只做两件事:
1. 红线索引——中心套件保留一条断网哨兵,确保 RL11 在 tests/security 可见;
2. 补越界**写**负例(S5);并以 xfail **固化已知边界**:SubprocessRunner 为注入式 best-effort,
   `os.system` 等启子进程的调用可逃逸进程内护栏,真正强隔离由生产 ContainerRunner 承担(§12.4)。

铁律:不得把"逃逸被拦"写成假绿;残留风险以 xfail(strict=False)显式留痕,而非删除/掩盖。
"""

from __future__ import annotations

import os
import tempfile

import pytest

from sandbox_svc import SandboxRequest, SubprocessRunner


def test_write_outside_sandbox_blocked() -> None:
    target = os.path.join(tempfile.gettempdir(), "sandbox_write_escape.txt")
    result = SubprocessRunner().run(
        SandboxRequest(code=f"open({target!r}, 'w').write('x')\n", timeout_s=30)
    )
    assert not result.ok
    assert "outside sandbox" in result.stderr  # 写越界被 open 护栏拦下


def test_network_blocked_sentinel() -> None:
    # 红线索引哨兵(与 sandbox-svc 穷举一致):socket 创建即抛错。
    result = SubprocessRunner().run(
        SandboxRequest(code="import socket\nsocket.socket()\n", timeout_s=30)
    )
    assert not result.ok
    assert "network" in result.stderr.lower()


@pytest.mark.xfail(
    reason="SubprocessRunner 为注入式 best-effort:os.system 子进程逃逸进程内护栏;"
    "真正强隔离见生产 ContainerRunner(§12.4)。此处固化已知残留,若哪天被拦将 xpass 提醒收紧。",
    strict=False,
)
def test_os_system_should_be_blocked_known_residual() -> None:
    # 理想:os.system 启动外部进程应被拦,致用户代码失败。现实 best-effort 实现拦不住 echo → ok=True。
    result = SubprocessRunner().run(
        SandboxRequest(code="import os\nos.system('echo hi')\n", timeout_s=30)
    )
    assert not result.ok
