"""SQL 校验层(红线 6 的载体)。纯函数,无 DB,逐项可测。

流水:解析(单条)→ 只读断言(禁 DML/DDL)→ 表白名单 → RLS 注入(每个 SELECT 作用域,
含子查询/CTE)→ 强制 LIMIT。任一不过即拒(VALIDATION_FAILED),绝无"测试态放行"开关。
"""

from __future__ import annotations

from typing import cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import traverse_scope

from .errors import ValidationError
from .models import Lineage, RlsApplied, ValidatedQuery
from .semantic_layer import SemanticLayer

_DIALECT = "postgres"
_DEFAULT_MAX_ROWS = 1000

# 任一出现即拒:写操作 / DDL / 原始命令 / SELECT…INTO / SET / COPY。
# 注:DML 藏在 CTE(WITH t AS (DELETE … RETURNING *))也会被 find_all 命中。
_FORBIDDEN: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Merge,
    exp.Command,
    exp.Into,
    exp.Set,
    exp.Copy,
)


class SqlValidator:
    def __init__(self, semantic: SemanticLayer, *, max_rows: int = _DEFAULT_MAX_ROWS) -> None:
        self._sem = semantic
        self._max_rows = max_rows

    def validate(self, sql: str, *, tenant_id: str) -> ValidatedQuery:
        tree = self._parse_single(sql)
        self._assert_read_only(tree)
        rls_applied = self._check_tables_and_inject_rls(tree, tenant_id=tenant_id)
        limit = self._enforce_limit(tree)
        tables = sorted({a.table for a in rls_applied} | self._base_table_names(tree))
        lineage = Lineage(tables=tables, rls_applied=rls_applied, limit=limit)
        return ValidatedQuery(sql=tree.sql(dialect=_DIALECT), lineage=lineage)

    # ---- 各阶段 ---------------------------------------------------------- #
    def _parse_single(self, sql: str) -> exp.Expression:
        try:
            statements = sqlglot.parse(sql, read=_DIALECT)
        except ParseError as exc:
            raise ValidationError("SQL 解析失败") from exc
        nonnull = [s for s in statements if s is not None]
        if len(nonnull) != 1:
            raise ValidationError("仅允许单条 SELECT 语句")
        # sqlglot.parse 返回 list[Expr | None](Expr 为 bound=Expression 的 TypeVar);收窄到具体类型。
        return cast("exp.Expression", nonnull[0])

    def _assert_read_only(self, tree: exp.Expression) -> None:
        if next(tree.find_all(*_FORBIDDEN), None) is not None:
            raise ValidationError("禁止 DML/DDL 操作")
        if tree.find(exp.Select) is None:
            raise ValidationError("仅允许 SELECT 查询")

    def _cte_names(self, tree: exp.Expression) -> set[str]:
        return {cte.alias_or_name for cte in tree.find_all(exp.CTE)}

    def _base_table_names(self, tree: exp.Expression) -> set[str]:
        ctes = self._cte_names(tree)
        return {t.name for t in tree.find_all(exp.Table) if t.name not in ctes}

    def _check_tables_and_inject_rls(
        self, tree: exp.Expression, *, tenant_id: str
    ) -> list[RlsApplied]:
        ctes = self._cte_names(tree)
        applied: list[RlsApplied] = []
        for scope in traverse_scope(tree):
            select = scope.expression
            if not isinstance(select, exp.Select):
                continue
            for table in scope.tables:
                name = table.name
                if name in ctes:
                    continue  # CTE 引用不是基表
                if not self._sem.is_allowed(name):
                    raise ValidationError(f"表不在白名单:{name}")
                tcol = self._sem.tenant_column(name)
                if tcol is None:
                    continue
                predicate = exp.EQ(
                    this=exp.column(tcol, table=table.alias_or_name),
                    expression=exp.Literal.string(tenant_id),
                )
                select.where(predicate, append=True, copy=False)
                applied.append(RlsApplied(table=name, predicate=predicate.sql(dialect=_DIALECT)))
        return applied

    def _enforce_limit(self, tree: exp.Expression) -> int:
        if not isinstance(tree, exp.Select):
            # UNION / 子查询等:无条件套一层 LIMIT 上限
            tree.set("limit", exp.Limit(expression=exp.Literal.number(self._max_rows)))
            return self._max_rows
        existing = tree.args.get("limit")
        current = self._existing_limit(existing)
        if current is not None and current <= self._max_rows:
            return current
        tree.limit(self._max_rows, copy=False)
        return self._max_rows

    @staticmethod
    def _existing_limit(limit_node: exp.Expression | None) -> int | None:
        if limit_node is None or not isinstance(limit_node, exp.Limit):
            return None
        try:
            return int(limit_node.expression.name)
        except (AttributeError, ValueError):
            return None
