"""开场注入(方案 §4.3 / §6.2 / §7.2):画像 + 相关记忆/经验 TopK + Skill 索引,各设 token 上限。

经现成 build_system_prompt 注入(skills_index / memories / experiences 段)。各段按 token 估算截断。
"""

from __future__ import annotations

from contracts import UserCtx
from memory_svc import MemoryService

from .skills import SkillIndex
from .system_prompt import build_system_prompt

_CHARS_PER_TOKEN = 4
# 各注入段 token 上限(§4.3 精神;可调)。
SKILLS_CAP = 400
MEMORY_CAP = 500
EXPERIENCE_CAP = 500


def cap_tokens(text: str, max_tokens: int) -> str:
    limit = max_tokens * _CHARS_PER_TOKEN
    return text if len(text) <= limit else text[:limit] + "…"


async def opening_system_prompt(
    user_ctx: UserCtx,
    memory_service: MemoryService,
    skill_index: SkillIndex,
    *,
    query: str = "",
) -> str:
    skills_index = cap_tokens(skill_index.render_index(), SKILLS_CAP)
    ctx = await memory_service.opening_context(user_ctx, query=query)
    memory_lines = [f"画像:{p}" for p in ctx.profile] + [f"记忆:{h.content}" for h in ctx.memories]
    memories = cap_tokens("\n".join(memory_lines), MEMORY_CAP)
    experiences = cap_tokens(
        "\n".join(f"经验:{h.content}" for h in ctx.experiences), EXPERIENCE_CAP
    )
    return build_system_prompt(
        skills_index=skills_index, memories=memories, experiences=experiences
    )
