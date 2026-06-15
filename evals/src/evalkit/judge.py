"""评分判定(§10 双轨):RuleJudge(确定性规则,主轨)+ LlmJudge(provider 接口,默认不触发)。

RuleJudge 检查答案是否覆盖关键依据(grounding),不把标准答案喂回模型;
LlmJudge 仅在注入真实 provider 时启用(留接口,无 API key 不触发)。
"""

from __future__ import annotations

from typing import Protocol

from llm import Message, Provider, Role, TextBlock


class Judge(Protocol):
    async def grade(self, *, answer: str, must_include: list[str]) -> tuple[bool, str]: ...


class RuleJudge:
    """规则判定:答案须包含全部关键短语(检索 grounding 检查)。"""

    async def grade(self, *, answer: str, must_include: list[str]) -> tuple[bool, str]:
        missing = [k for k in must_include if k not in answer]
        if missing:
            return False, f"答案缺少关键依据:{missing}"
        return True, ""


class LlmJudge:
    """LLM-as-judge 接口(经 packages/llm provider)。仅在配置真实 provider 时启用。"""

    def __init__(self, provider: Provider) -> None:
        self._provider = provider

    async def grade(self, *, answer: str, must_include: list[str]) -> tuple[bool, str]:
        criteria = "、".join(must_include)
        prompt = f"判断下面回答是否覆盖要点[{criteria}]。只回 PASS 或 FAIL。\n回答:{answer}"
        resp = await self._provider.complete(
            system="你是严格的评估裁判,只输出 PASS 或 FAIL。",
            messages=[Message(role=Role.user, content=[TextBlock(prompt)])],
        )
        verdict = resp.text.strip().upper()
        return verdict.startswith("PASS"), f"llm-judge={verdict}"
