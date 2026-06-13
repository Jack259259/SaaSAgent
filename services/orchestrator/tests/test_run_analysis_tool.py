"""run_analysis 工具 handler:正例(工作区句柄往返)+ 越权被拒(红线 3)。"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from contracts import ToolSpec, UserCtx
from contracts.loader import load_toolspecs
from orchestrator import NoPermissionError, ToolContext, ToolRegistry, Workspace
from orchestrator.tools import make_run_analysis_handler
from sandbox_svc import SubprocessRunner


def _uc(perms: Sequence[str] = ("*",)) -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["a"], data_scope={}, permissions=list(perms)
    )


def _run_analysis_spec() -> ToolSpec:
    return next(ls.spec for ls in load_toolspecs() if ls.spec.name == "run_analysis")


async def test_run_analysis_produces_artifact_handle() -> None:
    ws = Workspace()
    csv_ref = ws.put(
        key="data",
        type="sql_result",
        summary="csv",
        raw="region,amount\neast,10\neast,20\nwest,30\n",
    )
    ctx = ToolContext(user_ctx=_uc(), workspace=ws, trace_id="t")
    handler = make_run_analysis_handler(SubprocessRunner())
    code = (
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n"
        "df = pd.read_csv(INPUTS[0])\n"
        "df.groupby('region')['amount'].sum().plot(kind='bar')\n"
        "plt.savefig(OUTPUT_DIR + '/out.png')\n"
        "print('done')\n"
    )
    out = await handler({"code": code, "input_handles": [csv_ref], "timeout_s": 60}, ctx)
    assert not out.is_error, out.summary
    refs = out.raw["artifacts"]
    assert len(refs) == 1
    artifact = ws.get(refs[0]).raw
    assert isinstance(artifact, bytes)
    assert artifact[:8] == b"\x89PNG\r\n\x1a\n"


async def test_run_analysis_is_permission_gated() -> None:
    registry = ToolRegistry()
    registry.register(_run_analysis_spec(), make_run_analysis_handler(SubprocessRunner()))
    ctx = ToolContext(user_ctx=_uc(perms=[]), workspace=Workspace(), trace_id="t")
    with pytest.raises(NoPermissionError):  # 红线 3:沙箱工具同样二次校验权限
        await registry.invoke("run_analysis", {"code": "print(1)"}, ctx)
