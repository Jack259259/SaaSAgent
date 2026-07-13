"""WrenLocalEngine:嵌入式 WrenAI NL2SQL 引擎(pip 包 wrenai,可选 extra "wren")。

分工(docs/integration/wrenai.md):SQL 由本仓统一 LLM 通道(packages/llm Provider,
装配期注入)生成;wren 侧只做语义层装载、strict 策略校验(拒 manifest 外表/数据读取函数)
与 dry_plan 方言转换 —— 纯变换、无数据库连接。执行仍走 ReadOnlyExecutor,
SqlValidator(红线 6)在 DataService 内继续硬闸,本引擎不旁路任何校验。

自纠分两层、正交:本引擎内部用 dry_plan 失败信息自纠(纠语法/语义层错,≤max_internal_retries);
外层 DataService 用 executor.explain 失败信息自纠(纠真实库执行错,如坏列名 ——
wren dry_plan 不校验列存在性,实测见 docs/integration/wrenai.md)。

红线 7 口径:schema 上下文 / 业务规则 / few-shot 来自 assets/semantic-layer/wren/
(仓内受控资产,评审 + 评估门禁,红线 10)→ 允许进 system 位;用户问句与
prior_error / dry_plan 错误回流属不可信数据 → 只进 user 消息,并以 <question> /
<prior_error> 分隔标记包裹。最终安全不依赖提示词,由校验层兜底。

wrenai 惰性导入:未装 extra / 语义层目录缺失 → NOT_CONFIGURED(与 WrenAdapter 同口径)。
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx
import yaml

from contracts import UserCtx
from llm import Message, Role, TextBlock
from llm import NotConfiguredError as LlmNotConfiguredError
from llm import Provider as LlmProvider

from .errors import NotConfiguredError, QueryTimeoutError, ValidationError
from .models import Clarification, Nl2SqlResult

_DEFAULT_PROJECT_DIR = Path("assets/semantic-layer/wren")
_DEFAULT_PROMPT_PATH = Path("assets/prompts/nl2sql/v1.md")
_SQL_FENCE = re.compile(r"```sql\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_ANY_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\s*\n(.*?)```", re.DOTALL)


@runtime_checkable
class WrenPlanner(Protocol):
    """wren 侧最小接缝:校验+方言转换一体(dry_plan)。

    失败必须抛异常(异常信息作为自纠数据回流);成功返回目标方言(postgres/GaussDB
    PG 兼容口径)的可执行 SQL。真实实现 _WrenCorePlanner;测试注入替身。
    """

    def plan(self, sql: str) -> str: ...


# ---- 语义层资产装载(纯 YAML/文本,不依赖 wrenai;与 wren v0.13 文件格式对齐) ---- #


@dataclass(frozen=True)
class WrenKnowledge:
    rules: str
    examples: list[tuple[str, str]]  # (问句, SQL)


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """knowledge/sql/*.md 的 YAML frontmatter(与 wren.memory.markdown 同格式)。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            data = yaml.safe_load("\n".join(lines[1:i]))
            return data if isinstance(data, dict) else {}
    return {}


def load_knowledge(project_dir: Path) -> WrenKnowledge:
    rules_parts = [
        f.read_text("utf-8").strip()
        for f in sorted((project_dir / "knowledge" / "rules").glob("*.md"))
    ]
    examples: list[tuple[str, str]] = []
    for f in sorted((project_dir / "knowledge" / "sql").glob("*.md")):
        data = _parse_frontmatter(f.read_text("utf-8"))
        nl, sql = data.get("nl"), data.get("sql")
        if nl and sql:
            examples.append((str(nl).strip(), str(sql).strip()))
    return WrenKnowledge(rules="\n\n".join(rules_parts), examples=examples)


def render_schema_context(project_dir: Path) -> str:
    """models/*/metadata.yml + relationships.yml → 紧凑 schema 文本(全量入提示词)。"""
    blocks: list[str] = []
    for f in sorted((project_dir / "models").glob("*/metadata.yml")):
        m = yaml.safe_load(f.read_text("utf-8"))
        desc = (m.get("properties") or {}).get("description", "")
        cols = []
        for c in m.get("columns") or []:
            note = (c.get("properties") or {}).get("description", "")
            pk = ",主键" if c.get("is_primary_key") else ""
            cols.append(
                f"  - {c['name']} {c.get('type', '')}{pk}" + (f" —— {note}" if note else "")
            )
        head = f"表 {m['name']}" + (f"({desc})" if desc else "")
        blocks.append(head + ":\n" + "\n".join(cols))
    rel_file = project_dir / "relationships.yml"
    if rel_file.exists():
        rels = (yaml.safe_load(rel_file.read_text("utf-8")) or {}).get("relationships") or []
        if rels:
            lines = [f"  - {r['condition']}({r.get('join_type', '')})" for r in rels]
            blocks.append("表间关联:\n" + "\n".join(lines))
    return "\n\n".join(blocks)


# ---- 模型输出解析(纯函数,独立可测) ------------------------------------------ #


def extract_sql(text: str) -> str | None:
    """取最后一个 ```sql 围栏;无则取内容以 SELECT/WITH 开头的最后一个通用围栏;
    再无则接受整体以 SELECT/WITH 开头的裸文本。去尾分号。"""
    candidates = [m.group(1) for m in _SQL_FENCE.finditer(text)]
    if not candidates:
        candidates = [
            m.group(1)
            for m in _ANY_FENCE.finditer(text)
            if m.group(1).lstrip().upper().startswith(("SELECT", "WITH"))
        ]
    if not candidates:
        stripped = text.strip()
        if stripped.upper().startswith(("SELECT", "WITH")):
            candidates = [stripped]
    if not candidates:
        return None
    sql = candidates[-1].strip().rstrip(";").strip()
    return sql or None


def extract_clarifications(text: str) -> list[Clarification]:
    """解析 {"clarifications": [...]}(裸 JSON 或围栏内 JSON);解析不出即空列表。"""
    candidates = [m.group(1) for m in _ANY_FENCE.finditer(text)]
    stripped = text.strip()
    if stripped.startswith("{"):
        candidates.append(stripped)
    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        items = data.get("clarifications") if isinstance(data, dict) else None
        if not isinstance(items, list):
            continue
        out: list[Clarification] = []
        for item in items:
            if not isinstance(item, dict) or "field" not in item or "question" not in item:
                continue
            options = item.get("options")
            out.append(
                Clarification(
                    field=str(item["field"]),
                    question=str(item["question"]),
                    options=[str(o) for o in options] if isinstance(options, list) else [],
                )
            )
        if out:
            return out
    return []


# ---- 真实 wren 实现(惰性 import;wren 面收敛于此,升级只动这里) ----------------- #


class _WrenCorePlanner:
    """wren.engine.WrenEngine 的 dry_plan 封装:strict 策略 + fallback=False。

    - 空 connection_info = transpile-only(引擎源码明示,无数据库连接);
    - strict_mode:拒 manifest 外的表与数据读取函数(read_csv/dblink 等);
    - fallback=False:语法错在 planning 期即抛(错误信息供自纠);
    - 列存在性 dry_plan 不校验 —— 由外层 executor.explain 兜底(引擎实测)。
    """

    def __init__(self, project_dir: Path) -> None:
        from wren.config import WrenConfig
        from wren.context import build_json
        from wren.engine import WrenEngine

        manifest = build_json(project_dir)
        manifest_str = base64.b64encode(json.dumps(manifest).encode()).decode()
        data_source = manifest.get("dataSource") or "postgres"
        self._engine = WrenEngine(
            manifest_str, data_source, {}, fallback=False, config=WrenConfig(strict_mode=True)
        )

    def plan(self, sql: str) -> str:
        return str(self._engine.dry_plan(sql))


# ---- 引擎 -------------------------------------------------------------------- #


class WrenLocalEngine:
    """NL2SQLEngine 实现:受控资产提示词 + 统一 LLM 通道 + wren dry_plan 校验/转换。"""

    def __init__(
        self,
        *,
        provider: LlmProvider,
        project_dir: Path | None = None,
        prompt_path: Path | None = None,
        planner: WrenPlanner | None = None,
        max_internal_retries: int = 1,
        max_tokens: int = 2048,
    ) -> None:
        # 构造必须廉价且不抛错:缺资产/缺依赖在首次调用时以 NOT_CONFIGURED 暴露(同 WrenAdapter)。
        env_dir = os.environ.get("FP_WREN_PROJECT_DIR", "").strip()
        self._project_dir = project_dir or (Path(env_dir) if env_dir else _DEFAULT_PROJECT_DIR)
        self._prompt_path = prompt_path or _DEFAULT_PROMPT_PATH
        self._provider = provider
        self._planner = planner
        self._max_internal_retries = max_internal_retries
        self._max_tokens = max_tokens
        self._system: str | None = None
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "wren_local"

    async def generate(
        self, question: str, user_ctx: UserCtx, *, prior_error: str | None = None
    ) -> Nl2SqlResult:
        planner = await self._ensure_planner()
        system = await self._ensure_system()
        messages = [_user_message(_question_block(question, prior_error))]
        for _ in range(self._max_internal_retries + 1):
            resp_text = await self._complete(system, messages)
            clarifications = extract_clarifications(resp_text)
            if clarifications:
                return Nl2SqlResult(clarifications=clarifications)
            sql = extract_sql(resp_text)
            if sql is None:
                raise ValidationError("模型未产出可解析的 SQL")
            try:
                planned = await asyncio.to_thread(planner.plan, sql)
            except Exception as exc:  # planner 失败信息一律作数据回流自纠(接缝约定:失败即抛)
                messages.append(Message(role=Role.assistant, content=[TextBlock(resp_text)]))
                messages.append(_user_message(_correction_block(str(exc))))
                continue
            return Nl2SqlResult(sql=planned)
        raise ValidationError("生成的 SQL 未通过语义层校验(内部自纠超限)")

    # ---- 内部 ----------------------------------------------------------- #

    async def _ensure_planner(self) -> WrenPlanner:
        planner = self._planner
        if planner is None:
            async with self._lock:
                planner = self._planner
                if planner is None:
                    planner = await asyncio.to_thread(self._build_planner)
                    self._planner = planner
        return planner

    def _build_planner(self) -> WrenPlanner:
        if not self._project_dir.is_dir():
            raise NotConfiguredError(f"Wren 语义层项目缺失:{self._project_dir}")
        try:
            return _WrenCorePlanner(self._project_dir)
        except ImportError as exc:
            raise NotConfiguredError("wrenai 未安装(uv sync --all-packages --extra wren)") from exc

    async def _ensure_system(self) -> str:
        system = self._system
        if system is None:
            async with self._lock:
                system = self._system
                if system is None:
                    system = await asyncio.to_thread(self._build_system)
                    self._system = system
        return system

    def _build_system(self) -> str:
        if not self._prompt_path.is_file():
            raise NotConfiguredError(f"NL2SQL 提示词缺失:{self._prompt_path}")
        template = self._prompt_path.read_text("utf-8")
        knowledge = load_knowledge(self._project_dir)
        examples = "\n\n".join(
            f"### 示例 {i}\n问:{nl}\n```sql\n{sql}\n```"
            for i, (nl, sql) in enumerate(knowledge.examples, start=1)
        )
        # 用 replace 而非 str.format:SQL/规则文本里的花括号不做转义(模板占位符是 {{TOKEN}})。
        return (
            template.replace("{{SCHEMA_CONTEXT}}", render_schema_context(self._project_dir))
            .replace("{{RULES}}", knowledge.rules)
            .replace("{{EXAMPLES}}", examples)
        )

    async def _complete(self, system: str, messages: list[Message]) -> str:
        start = time.perf_counter()
        try:
            resp = await self._provider.complete(
                system=system, messages=messages, max_tokens=self._max_tokens
            )
        except LlmNotConfiguredError as exc:
            raise NotConfiguredError("LLM 未配置(见 config/llm.yml)") from exc
        except (TimeoutError, httpx.TimeoutException) as exc:
            elapsed = (time.perf_counter() - start) * 1000
            raise QueryTimeoutError(f"LLM 调用超时({elapsed:.0f}ms)") from exc
        return resp.text


def _user_message(text: str) -> Message:
    return Message(role=Role.user, content=[TextBlock(text)])


def _question_block(question: str, prior_error: str | None) -> str:
    # 问句与错误回流是不可信数据:标记包裹,只进 user 位(红线 7)。
    parts = [f"<question>\n{question}\n</question>"]
    if prior_error:
        parts.append(f"<prior_error>\n{prior_error}\n</prior_error>")
    return "\n".join(parts)


def _correction_block(error: str) -> str:
    return f"<prior_error>\n{error}\n</prior_error>\n据此修正后重新输出完整 SQL。"
