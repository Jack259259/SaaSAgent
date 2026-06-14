"""语义层:表白名单 + 每表 RLS 配置(assets/semantic-layer/tables.yaml)。

事实源是 assets 下的 yaml(资产,走评审,红线 10);此处只做加载与查询。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_TABLES_PATH = Path("assets/semantic-layer/tables.yaml")


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[str, ...]
    tenant_column: str | None  # None = 该表无 RLS(仍受白名单约束)


@dataclass(frozen=True)
class SemanticLayer:
    tables: dict[str, TableSpec]

    def is_allowed(self, table: str) -> bool:
        return table in self.tables

    def tenant_column(self, table: str) -> str | None:
        spec = self.tables.get(table)
        return spec.tenant_column if spec else None

    @classmethod
    def load(cls, path: Path | None = None) -> SemanticLayer:
        raw: dict[str, Any] = (
            yaml.safe_load((path or _DEFAULT_TABLES_PATH).read_text("utf-8")) or {}
        )
        tables: dict[str, TableSpec] = {}
        for name, body in (raw.get("tables") or {}).items():
            body = body or {}
            rls = body.get("rls") or {}
            tables[name] = TableSpec(
                name=name,
                columns=tuple(body.get("columns") or ()),
                tenant_column=rls.get("tenant_column"),
            )
        return cls(tables=tables)
