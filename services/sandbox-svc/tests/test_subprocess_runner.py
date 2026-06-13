"""红线 11 验收:run_analysis 受限沙箱的隔离负例 + 正例。

负例必须全过。CPU/内存 rlimit 仅 POSIX → 内存负例 skipif(win32),CI(Linux)强制执行;
网络/路径/超时/import 负例跨平台(本机 + CI 均运行)。
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

from sandbox_svc import SandboxInput, SandboxRequest, SubprocessRunner


# ---- 红线 11 负例(跨平台)------------------------------------------------ #
def test_network_socket_blocked() -> None:
    result = SubprocessRunner().run(
        SandboxRequest(code="import socket\nsocket.socket()\n", timeout_s=30)
    )
    assert not result.ok
    assert "network" in result.stderr.lower()


def test_read_outside_sandbox_blocked() -> None:
    escape = os.path.join(tempfile.gettempdir(), "sandbox_escape_target.txt")
    result = SubprocessRunner().run(SandboxRequest(code=f"open({escape!r}).read()\n", timeout_s=30))
    assert not result.ok
    assert "outside sandbox" in result.stderr


def test_infinite_loop_timed_out() -> None:
    result = SubprocessRunner().run(SandboxRequest(code="while True:\n    pass\n", timeout_s=5.0))
    assert result.timed_out is True
    assert not result.ok


def test_non_whitelisted_import_blocked() -> None:
    result = SubprocessRunner().run(SandboxRequest(code="import requests\n", timeout_s=30))
    assert not result.ok
    assert "not allowed" in result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="RLIMIT_AS 仅 POSIX;CI(Linux)强制")
def test_memory_limit_kills() -> None:
    result = SubprocessRunner().run(
        SandboxRequest(
            code="data = bytearray(300 * 1024 * 1024)\nprint(len(data))\n",
            timeout_s=30,
            mem_headroom_bytes=128 * 1024 * 1024,
        )
    )
    assert not result.ok


# ---- 正例 ----------------------------------------------------------------- #
def test_csv_groupby_and_savefig_png() -> None:
    code = (
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n"
        "df = pd.read_csv(INPUTS[0])\n"
        "summary = df.groupby('region')['amount'].sum()\n"
        "print(summary.to_dict())\n"
        "summary.plot(kind='bar')\n"
        "plt.savefig(OUTPUT_DIR + '/chart.png')\n"
    )
    csv = b"region,amount\neast,10\neast,20\nwest,30\n"
    result = SubprocessRunner().run(
        SandboxRequest(code=code, inputs=[SandboxInput("in.csv", csv)], timeout_s=60)
    )
    assert result.ok, result.stderr
    assert "chart.png" in result.artifacts
    assert result.artifacts["chart.png"][:8] == b"\x89PNG\r\n\x1a\n"
    assert "east" in result.stdout
