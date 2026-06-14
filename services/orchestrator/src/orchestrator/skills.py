"""Skill 装载(方案 §6):assets/skills/<name>/SKILL.md(YAML frontmatter + 正文)。

渐进式披露:系统提示只注入索引(name + description);load_skill 按名取全文。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_SKILLS_DIR = Path("assets/skills")


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    triggers: tuple[str, ...] = ()
    body: str = ""


def _parse_skill_md(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            meta = yaml.safe_load(parts[1]) or {}
            if isinstance(meta, dict):
                return meta, parts[2].strip()
    return {}, text.strip()


@dataclass
class SkillIndex:
    skills: dict[str, Skill] = field(default_factory=dict)

    @classmethod
    def load(cls, skills_dir: Path = _DEFAULT_SKILLS_DIR) -> SkillIndex:
        skills: dict[str, Skill] = {}
        if skills_dir.exists():
            for md in sorted(skills_dir.glob("*/SKILL.md")):
                meta, body = _parse_skill_md(md.read_text("utf-8"))
                name = str(meta.get("name") or md.parent.name)
                skills[name] = Skill(
                    name=name,
                    description=str(meta.get("description", "")),
                    triggers=tuple(str(t) for t in (meta.get("triggers") or [])),
                    body=body,
                )
        return cls(skills=skills)

    def render_index(self) -> str:
        """仅 name + description(+ 触发场景),供系统提示注入(§6.2)。"""
        return "\n".join(
            f"- {s.name}:{s.description}" + (f"(触发:{'/'.join(s.triggers)})" if s.triggers else "")
            for s in self.skills.values()
        )

    def load_body(self, name: str) -> str | None:
        skill = self.skills.get(name)
        return skill.body if skill is not None else None
