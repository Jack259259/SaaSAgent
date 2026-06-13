"""schema 与工具规格的加载器。

加载即"读 → jsonschema 校验 → 构造 pydantic 模型",保证以 schema 文件为事实源。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .models import LoadedToolSpec, ToolSpec
from .paths import find_contracts_dir

# 逻辑名 → 相对 contracts/ 的路径
SCHEMA_RELPATHS: dict[str, str] = {
    "toolspec": "toolspec/_schema.json",
    "envelope": "toolspec/envelope.json",
    "agent_state": "agent-state/schema.json",
    "audit": "events/audit.json",
    "sop": "sop/_schema.yaml",
}

# 领域工具的细分域(docs 表"域"列用);base 工具统一为 "base"。
_DOMAIN_BY_NAME: dict[str, str] = {
    "search_knowledge": "rag",
    "query_finance_data": "data",
    "ask_codebase": "code",
    "find_sop": "sop",
    "run_sop": "sop",
}


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data: Any = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 顶层不是对象")
    return data


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data: Any = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 顶层不是对象")
    return data


def load_doc(path: Path) -> dict[str, Any]:
    """按扩展名加载 JSON / YAML 文档为 dict。"""
    if path.suffix in (".yaml", ".yml"):
        return _read_yaml(path)
    return _read_json(path)


def schema_path(name: str) -> Path:
    return find_contracts_dir() / SCHEMA_RELPATHS[name]


def load_schema(name: str) -> dict[str, Any]:
    """加载一个命名 schema 文档(name ∈ SCHEMA_RELPATHS)。"""
    return load_doc(schema_path(name))


def load_all_schemas() -> dict[str, dict[str, Any]]:
    return {name: load_schema(name) for name in SCHEMA_RELPATHS}


def iter_toolspec_paths() -> list[Path]:
    """domain/ 与 base/ 下全部工具规格 YAML 路径(稳定排序)。"""
    d = find_contracts_dir() / "toolspec"
    domain = sorted((d / "domain").glob("*.yaml"))
    base = sorted((d / "base").glob("*.yaml"))
    return domain + base


def classify_domain(name: str, parent_dir: str) -> str:
    if parent_dir == "base":
        return "base"
    return _DOMAIN_BY_NAME.get(name, "domain")


def load_toolspecs() -> list[LoadedToolSpec]:
    """加载全部工具规格:逐份 jsonschema 校验后构造 ToolSpec。"""
    from .validator import validate_toolspec  # 延迟导入,避免与 validator 形成导入环

    out: list[LoadedToolSpec] = []
    for path in iter_toolspec_paths():
        raw = load_doc(path)
        validate_toolspec(raw)
        spec = ToolSpec.model_validate(raw)
        out.append(
            LoadedToolSpec(
                spec=spec, domain=classify_domain(spec.name, path.parent.name), path=path
            )
        )
    return out
