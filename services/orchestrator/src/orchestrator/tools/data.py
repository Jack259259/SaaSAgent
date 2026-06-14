"""query_finance_data 工具 handler(§5.2)。

适配工具契约 ↔ DataService:取数(NL→SQL→校验层 RLS→只读执行→自纠)。结果"摘要 + 表格句柄"
(红线 8),最终 SQL 与 lineage 透出供核对。AMBIGUOUS_FIELD 以"摘要 + 选项"非错误结果透出,
由模型据此调 ask_user(§5.2,薄循环不加硬编码分支)。
审计:问句 + 最终 SQL + 行数 + 耗时(不记结果明细行,§6)。
"""

from __future__ import annotations

from typing import Any

import structlog

from contracts.models import ErrorCode
from data_svc import (
    AmbiguousFieldError,
    DataService,
    DataSvcError,
    NotConfiguredError,
)

from ..registry import ToolHandler, ToolOutcome
from ..tool_context import ToolContext

_log = structlog.get_logger("orchestrator.tools.data")


def make_query_finance_data_handler(data_service: DataService) -> ToolHandler:
    async def query_finance_data(args: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        question = str(args.get("question", ""))
        try:
            result = await data_service.query(question, ctx.user_ctx)
        except AmbiguousFieldError as exc:
            options = "; ".join(f"{c.field}({'/'.join(c.options)})" for c in exc.clarifications)
            return ToolOutcome(
                summary=f"字段或口径有歧义,需澄清:{options}",
                raw={
                    "error_code": ErrorCode.AMBIGUOUS_FIELD.value,
                    "clarifications": [c.model_dump() for c in exc.clarifications],
                },
            )
        except NotConfiguredError:
            return ToolOutcome(summary="取数能力尚未配置(数据库 / WrenAI 未对接)", is_error=True)
        except DataSvcError:
            return ToolOutcome(summary="查询无法安全执行或未返回有效结果", is_error=True)

        table_ref = ctx.workspace.put(
            key="finance/table",
            type="table",
            summary=result.summary,
            raw={"columns": result.columns, "rows": result.rows},
        )
        # 审计(红线 6 / §6):问句 + 最终 SQL + 行数 + 耗时;不记结果明细行。
        _log.info(
            "data_query",
            question=question,
            final_sql=result.sql,
            row_count=result.row_count,
            elapsed_ms=round(result.elapsed_ms, 1),
            engine=result.lineage.engine,
            tenant_id=ctx.user_ctx.tenant_id,
            user_id=ctx.user_ctx.user_id,
            trace_id=ctx.trace_id,
        )
        return ToolOutcome(
            summary=result.summary,
            raw={
                "summary": result.summary,
                "table_ref": table_ref,
                "sql": result.sql,
                "lineage": result.lineage.model_dump(),
            },
        )

    return query_finance_data
