"""load_skill 工具 handler(§6.2 渐进式披露):按名加载 Skill 全文进上下文。"""

from __future__ import annotations

from typing import Any

from ..registry import ToolHandler, ToolOutcome
from ..skills import SkillIndex
from ..tool_context import ToolContext


def make_load_skill_handler(skill_index: SkillIndex) -> ToolHandler:
    async def load_skill(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        name = str(args.get("name", ""))
        body = skill_index.load_body(name)
        if body is None:
            return ToolOutcome(summary=f"未找到 Skill:{name}", is_error=True)
        return ToolOutcome(summary=f"已加载 Skill:{name}", raw={"name": name, "content": body})

    return load_skill
