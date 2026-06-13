"""run_analysis 工具 handler(§5.5 / 红线 11)。

适配工具契约 ↔ sandbox-svc 运行器:输入句柄→只读文件挂载,执行后产物→新工作区句柄。
沙箱执行本身的隔离由 sandbox-svc 保证(无网络/无库连接/限额);本 handler 不放宽任何隔离。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sandbox_svc import SandboxInput, SandboxRequest, SandboxRunner

from ..registry import ToolHandler, ToolOutcome
from ..tool_context import ToolContext


def _to_bytes(raw: Any) -> bytes:
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, str):
        return raw.encode("utf-8")
    return json.dumps(raw, ensure_ascii=False, default=str).encode("utf-8")


def make_run_analysis_handler(runner: SandboxRunner) -> ToolHandler:
    async def run_analysis(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        code = str(args.get("code", ""))
        handles = args.get("input_handles") or []
        timeout_s = float(args.get("timeout_s", 10))

        inputs: list[SandboxInput] = []
        for index, ref in enumerate(handles):
            try:
                item = ctx.workspace.get(str(ref))
            except KeyError:
                return ToolOutcome(summary=f"输入句柄不存在:{ref}", is_error=True)
            ext = ".csv" if isinstance(item.raw, str) else ".bin"
            inputs.append(SandboxInput(name=f"input_{index}{ext}", data=_to_bytes(item.raw)))

        result = await asyncio.to_thread(
            runner.run, SandboxRequest(code=code, inputs=inputs, timeout_s=timeout_s)
        )

        artifact_refs: list[str] = []
        for name, data in result.artifacts.items():
            ref = ctx.workspace.put(
                key=f"analysis/{name}",
                type="artifact",
                summary=f"产物 {name}({len(data)} 字节)",
                raw=data,
            )
            artifact_refs.append(ref)

        raw = {"stdout": result.stdout, "artifacts": artifact_refs}
        if not result.ok:
            if result.timed_out:
                reason = "执行超时"
            else:
                lines = result.stderr.strip().splitlines()
                reason = lines[-1] if lines else "执行失败"
            return ToolOutcome(summary=f"分析失败:{reason}", raw=raw, is_error=True)
        return ToolOutcome(summary=f"分析完成,产物 {len(artifact_refs)} 个", raw=raw)

    return run_analysis
