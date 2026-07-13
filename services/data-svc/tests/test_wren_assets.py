"""Wren 语义层资产 ↔ tables.yaml 白名单一致性守护(红线 6/10)。

纯 YAML/文本校验,不 import wrenai —— CI 恒跑,与是否安装 extra "wren" 无关。
铁律清单见 assets/semantic-layer/wren/README.md。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import sqlglot
import yaml
from sqlglot import exp

_WREN_DIR = Path("assets/semantic-layer/wren")
_TABLES_YAML = Path("assets/semantic-layer/tables.yaml")


def _whitelist() -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(_TABLES_YAML.read_text("utf-8"))
    return dict(raw["tables"])


def _models() -> dict[str, dict[str, Any]]:
    models: dict[str, dict[str, Any]] = {}
    for f in sorted((_WREN_DIR / "models").glob("*/metadata.yml")):
        m = yaml.safe_load(f.read_text("utf-8"))
        models[m["name"]] = m
    return models


def _fewshot_pairs() -> list[tuple[str, dict[str, Any]]]:
    """knowledge/sql/*.md 的 frontmatter(与 wren.memory.markdown 同格式,本地解析免依赖)。"""
    pairs: list[tuple[str, dict[str, Any]]] = []
    for f in sorted((_WREN_DIR / "knowledge" / "sql").glob("*.md")):
        lines = f.read_text("utf-8").splitlines()
        assert lines and lines[0].strip() == "---", f"{f.name}: 缺 frontmatter"
        end = next(i for i in range(1, len(lines)) if lines[i].rstrip() == "---")
        data = yaml.safe_load("\n".join(lines[1:end]))
        pairs.append((f.name, data))
    return pairs


def test_models_match_whitelist_bidirectional() -> None:
    models, whitelist = _models(), _whitelist()
    assert set(models) == set(whitelist), (
        f"模型集合与白名单不一致: 仅模型有 {set(models) - set(whitelist)}, "
        f"仅白名单有 {set(whitelist) - set(models)}"
    )


def test_table_reference_is_bare_model_name() -> None:
    # 裸表名约定:与校验层白名单"末段匹配"口径一致,且占位 run_sql(DuckDB)可直接执行。
    # 真实表若需固定 schema,按 wren/README.md 调整此断言(表名=模型名是硬性不变量)。
    for name, m in _models().items():
        ref = m["table_reference"]
        assert ref["table"] == name, f"{name}: table_reference.table 必须等于模型名"
        assert not ref.get("catalog") and not ref.get("schema"), f"{name}: catalog/schema 应留空"


def test_model_columns_subset_of_whitelist_and_contain_tenant_column() -> None:
    whitelist = _whitelist()
    for name, m in _models().items():
        model_cols = {c["name"] for c in m["columns"]}
        allowed = set(whitelist[name]["columns"])
        assert model_cols <= allowed, f"{name}: 模型列超出白名单 {model_cols - allowed}"
        tenant_col = (whitelist[name].get("rls") or {}).get("tenant_column")
        assert tenant_col, f"{name}: 白名单缺 rls.tenant_column(取数表必须有租户列)"
        assert tenant_col in model_cols, f"{name}: 模型缺租户列 {tenant_col}(RLS 注入的物理前提)"


def test_relationships_reference_known_models() -> None:
    models = _models()
    raw = yaml.safe_load((_WREN_DIR / "relationships.yml").read_text("utf-8")) or {}
    for rel in raw.get("relationships") or []:
        for ref in rel["models"]:
            assert ref in models, f"relationship {rel['name']}: 未知模型 {ref}"


@pytest.mark.parametrize("fname,data", _fewshot_pairs())
def test_fewshot_pair_is_safe_single_select(fname: str, data: dict[str, Any]) -> None:
    assert data.get("nl"), f"{fname}: 缺 nl"
    sql = data.get("sql")
    assert sql, f"{fname}: 缺 sql"
    statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    assert len(statements) == 1, f"{fname}: few-shot 必须是单条语句"
    tree = statements[0]
    assert tree.find(exp.Select) is not None, f"{fname}: few-shot 必须是 SELECT"
    whitelist = _whitelist()
    for t in tree.find_all(exp.Table):
        assert t.name in whitelist, f"{fname}: 引用了白名单外的表 {t.name}"
    # 不教模型写租户过滤 —— 租户隔离由校验层注入(红线 6),few-shot 出现即违规。
    assert "tenant_id" not in sql, f"{fname}: few-shot 不得包含 tenant_id 过滤"


def test_fewshot_has_seed_examples() -> None:
    assert len(_fewshot_pairs()) >= 5, "few-shot 种子应至少 5 条"
