"""make eval E=sop-replay 的实现:回放 assets/sops 全量(auto-confirm),失败写 <id>.stale 标记。

无 --base-url 时对内置 demo_mock 回放(hermetic CI);给 --base-url 则对真实预发回放(漂移检测)。
回放 = 漂移检测,同时是 E2E 回归集(方案 §5.4)。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import httpx

from contracts import UserCtx

from .demo_mock import DemoMockApp
from .executor import SopExecutor
from .httpcaller import HttpCaller
from .loader import load_sops
from .models import RunStatus, Sop
from .steprunner import FakeUiRunner


def _replay_user_ctx() -> UserCtx:
    return UserCtx(
        tenant_id="replay", user_id="replay", roles=["internal"], data_scope={}, permissions=["*"]
    )


def _replay_inputs(sop: Sop) -> dict[str, Any]:
    return {inp.key: f"replay-{inp.key}" for inp in sop.inputs}


def _make_caller(base_url: str | None) -> HttpCaller:
    if base_url:
        return HttpCaller.for_base_url(base_url)
    transport = httpx.ASGITransport(app=DemoMockApp())
    return HttpCaller(httpx.AsyncClient(transport=transport, base_url="http://demo-mock"))


async def _replay_one(sop: Sop, base_url: str | None) -> bool:
    http = _make_caller(base_url)
    try:
        executor = SopExecutor(http=http, ui_runner=FakeUiRunner())
        user_ctx = _replay_user_ctx()
        state = await executor.submit(sop, _replay_inputs(sop), user_ctx)
        if state.status == RunStatus.paused:
            state = await executor.resume(state, sop, confirmed=True, user_ctx=user_ctx)
        return state.status == RunStatus.succeeded
    finally:
        await http.aclose()


async def replay_all(sops_dir: Path, *, base_url: str | None = None) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for sop_id, sop in load_sops(sops_dir).items():
        ok = await _replay_one(sop, base_url)
        results[sop_id] = ok
        stale = sops_dir / f"{sop_id}.stale"
        if ok:
            stale.unlink(missing_ok=True)
        else:
            stale.write_text("stale: SOP 回放失败,已在 Agent 侧下线该操作并告警。\n", "utf-8")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sop-replay", description="回放全量 SOP,失败标 stale")
    parser.add_argument("sops_dir", nargs="?", default="assets/sops")
    parser.add_argument("--base-url", default=None, help="真实预发地址;缺省用内置 demo_mock")
    args = parser.parse_args(argv)

    results = asyncio.run(replay_all(Path(args.sops_dir), base_url=args.base_url))
    failed = [sid for sid, ok in results.items() if not ok]
    for sid, ok in results.items():
        print(f"{'OK  ' if ok else 'STALE'} {sid}")
    print(f"sop-replay: {len(results)} SOP, {len(failed)} stale")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
