"""行内反思(§4.1 / §4.4):每个关键产物过校验器,失败带 critique 回流重试 ≤2,全程留痕。

确定性校验优先:默认校验器用工具的 output_schema 校验产物(红线无关,纯质量闸)。
LLM 自评(critique→revise)留接口,本阶段以确定性 schema 校验为默认。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from contracts import ToolSpec

from .registry import ToolOutcome


@dataclass(frozen=True)
class Verdict:
    tool: str
    ok: bool
    critique: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "ok": self.ok, "critique": self.critique}


class Verifier(Protocol):
    def __call__(self, outcome: ToolOutcome, spec: ToolSpec) -> Verdict: ...


def default_output_schema_verifier(outcome: ToolOutcome, spec: ToolSpec) -> Verdict:
    """默认校验:工具产物须符合其 output_schema;错误产物直接判负。"""
    if outcome.is_error:
        return Verdict(tool=spec.name, ok=False, critique=f"工具返回错误:{outcome.summary}")
    if outcome.raw is None:
        return Verdict(tool=spec.name, ok=True)  # 无结构化 raw 的工具不做 schema 校验
    validator = Draft202012Validator(spec.output_schema)
    errors = sorted(
        validator.iter_errors(outcome.raw), key=lambda e: [str(p) for p in e.absolute_path]
    )
    if errors:
        detail = "; ".join(
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors[:3]
        )
        return Verdict(tool=spec.name, ok=False, critique=f"输出不符合 output_schema:{detail}")
    return Verdict(tool=spec.name, ok=True)


class VerifierRegistry:
    """按工具名挂校验器;未注册则用默认 schema 校验器。"""

    def __init__(self) -> None:
        self._by_tool: dict[str, Verifier] = {}
        self._default: Verifier = default_output_schema_verifier

    def register(self, tool: str, verifier: Verifier) -> None:
        self._by_tool[tool] = verifier

    def verify(self, outcome: ToolOutcome, spec: ToolSpec) -> Verdict:
        verifier = self._by_tool.get(spec.name, self._default)
        return verifier(outcome, spec)
