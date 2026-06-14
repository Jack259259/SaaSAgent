"""ask_codebase 派发入口 + 代码检索分析子 Agent(方案 §5.1 / 红线 12)。

子 Agent 复用 Orchestrator(独立上下文 + 紧预算 + §5.1 专属系统提示 + 6 个专属代码工具,内联注册)。
handler 在内部跑子 Agent,**只回传结构化结论 + 证据**(探索噪音不回流主上下文)。
代码工具是内部实现细节(非 contracts);唯一对外契约是 ask_codebase。
"""

from __future__ import annotations

import json
import re
from typing import Any

from code_svc import CodeService, PathOutsideRepoError
from contracts import ToolSpec, UserCtx
from contracts.models import ErrorCode, SideEffect
from llm import Provider

from ..events import AnswerDeltaEvent, DoneEvent
from ..loop import Budget, Orchestrator
from ..registry import ToolHandler, ToolOutcome, ToolRegistry
from ..tool_context import ToolContext

_MAX_LINES = 12  # 工具摘要里最多列多少条证据行

_CODE_SYSTEM_PROMPT = (
    "你是代码检索分析子 Agent(内部研发/支持角色)。只能用这些工具:\n"
    "get_repo_map、search_code、find_definition、find_references、find_callers、read_file。\n"
    "策略:先 get_repo_map / search_code 定向,\n"
    "再用 find_* 跟踪符号与调用,read_file 读关键行段后给结论。\n"
    "禁止使用 update_plan / ask_user。\n"
    "完成时,最后一条消息只输出一个 JSON 对象(无多余文字、无代码围栏),字段:\n"
    "answer(字符串)、evidences(数组,元素含 file / line_range / snippet)、\n"
    "confidence(0–1 数字)、followups(字符串数组)。\n"
    "evidences 必须来自工具返回的真实 file / 行号 / snippet;无据则置空并降低 confidence。"
)


def _code_system_prompt() -> str:
    return _CODE_SYSTEM_PROMPT


class _AllowInternalChecker:
    """子 Agent 内部工具放行:外部闸已是 ask_codebase(code.read.ask);内部工具是实现细节。"""

    def check(self, user_ctx: UserCtx, spec: ToolSpec) -> None:
        return None


def _spec(name: str, props: dict[str, Any], required: list[str]) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"代码子 Agent 内部工具:{name}",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": required,
            "properties": props,
        },
        output_schema={"type": "object"},
        permission_scope=f"code.read.{name}",
        side_effects=SideEffect.read,
        confirmation_required=False,
        timeout_ms=15000,
        errors=[ErrorCode.VALIDATION_FAILED, ErrorCode.NOT_FOUND],
    )


def _evidence_lines(items: list[dict[str, Any]]) -> str:
    lines = [f"{it['file']}:{it['line']} {it['snippet']}" for it in items[:_MAX_LINES]]
    more = "" if len(items) <= _MAX_LINES else f"\n…(共 {len(items)} 条)"
    return "\n".join(lines) + more


def build_code_subagent_registry(code_service: CodeService) -> ToolRegistry:
    registry = ToolRegistry(checker=_AllowInternalChecker())

    async def search_code(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        hits = [h.model_dump() for h in code_service.search_code(str(args.get("query", "")))]
        body = _evidence_lines(hits) if hits else "无匹配"
        return ToolOutcome(summary=f"search_code 命中 {len(hits)} 处:\n{body}", raw={"hits": hits})

    async def find_definition(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        defs = [d.model_dump() for d in code_service.find_definition(str(args.get("name", "")))]
        body = "\n".join(f"{d['file']}:{d['start_line']} {d['kind']} {d['snippet']}" for d in defs)
        return ToolOutcome(
            summary=f"find_definition {len(defs)} 个:\n{body or '无'}", raw={"defs": defs}
        )

    async def find_references(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        refs = [r.model_dump() for r in code_service.find_references(str(args.get("name", "")))]
        return ToolOutcome(
            summary=f"find_references {len(refs)} 处:\n{_evidence_lines(refs) or '无'}",
            raw={"refs": refs},
        )

    async def find_callers(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        calls = [c.model_dump() for c in code_service.find_callers(str(args.get("name", "")))]
        body = "\n".join(f"{c['file']}:{c['line']} {c['caller']} | {c['snippet']}" for c in calls)
        return ToolOutcome(
            summary=f"find_callers {len(calls)} 处:\n{body or '无'}", raw={"calls": calls}
        )

    async def read_file(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        try:
            sl = code_service.read_file(
                str(args.get("path", "")),
                start_line=int(args.get("start_line", 1)),
                end_line=int(args["end_line"]) if args.get("end_line") is not None else None,
            )
        except (PathOutsideRepoError, FileNotFoundError):
            return ToolOutcome(summary="路径越界或不存在(仅限索引仓内)", is_error=True)
        return ToolOutcome(
            summary=f"{sl.file}:{sl.start_line}-{sl.end_line}\n{sl.text}", raw=sl.model_dump()
        )

    async def get_repo_map(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        budget = int(args["token_budget"]) if args.get("token_budget") is not None else None
        rm = code_service.get_repo_map(token_budget=budget)
        body = "\n".join(f"{e.file}:{e.name} [{e.kind}] {e.signature}" for e in rm.entries)
        return ToolOutcome(
            summary=f"repo map(共 {rm.total_symbols} 符号,截断={rm.truncated}):\n{body}",
            raw=rm.model_dump(),
        )

    name_props = {"name": {"type": "string"}}
    registry.register(_spec("search_code", {"query": {"type": "string"}}, ["query"]), search_code)
    registry.register(_spec("find_definition", name_props, ["name"]), find_definition)
    registry.register(_spec("find_references", name_props, ["name"]), find_references)
    registry.register(_spec("find_callers", name_props, ["name"]), find_callers)
    registry.register(
        _spec(
            "read_file",
            {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            ["path"],
        ),
        read_file,
    )
    registry.register(
        _spec("get_repo_map", {"token_budget": {"type": "integer"}}, []), get_repo_map
    )
    return registry


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_findings(text: str, stop_reason: str) -> dict[str, Any]:
    if stop_reason == "budget_exhausted":
        return {
            "answer": text or "预算内未得出完整结论(已达子 Agent 预算上限)。",
            "evidences": [],
            "confidence": 0.2,
            "followups": ["缩小问题范围或指定具体文件/函数后重试"],
        }
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return {"answer": text, "evidences": [], "confidence": 0.3, "followups": []}
    evidences = [
        {
            "file": str(e.get("file", "")),
            "line_range": str(e.get("line_range", "")),
            "snippet": str(e.get("snippet", "")),
        }
        for e in data.get("evidences", [])
        if isinstance(e, dict)
    ]
    return {
        "answer": str(data.get("answer", "")),
        "evidences": evidences,
        "confidence": float(data.get("confidence", 0.5)),
        "followups": [str(f) for f in data.get("followups", []) if isinstance(f, str)],
    }


def make_ask_codebase_handler(
    provider: Provider,
    code_service: CodeService,
    *,
    max_tool_calls: int = 8,
    max_tokens: int = 20000,
) -> ToolHandler:
    async def ask_codebase(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        question = str(args.get("question", ""))
        scope = args.get("scope")
        prompt = question if not scope else f"{question}\n(scope: {scope})"
        sub = Orchestrator(
            provider=provider,
            registry=build_code_subagent_registry(code_service),
            budget=Budget(max_steps=max_tool_calls, max_tokens=max_tokens),
            system_prompt=_code_system_prompt,
        )
        parts: list[str] = []
        stop_reason = "end_turn"
        # 红线 12:子 Agent 事件在此消费,不外传(探索噪音留在隔离上下文)。
        async for event in sub.run(
            user_ctx=ctx.user_ctx, user_message=prompt, trace_id=ctx.trace_id
        ):
            if isinstance(event, AnswerDeltaEvent):
                parts.append(event.text)
            elif isinstance(event, DoneEvent):
                stop_reason = event.stop_reason
        findings = _parse_findings("".join(parts).strip(), stop_reason)
        return ToolOutcome(summary=findings["answer"], raw=findings)

    return ask_codebase
