"""data-svc 错误,映射到 ToolSpec.errors 枚举(§6:不吞异常,不泄内部细节)。"""

from __future__ import annotations

from contracts.models import ErrorCode

from .models import Clarification


class DataSvcError(Exception):
    """data-svc 错误基类,携带统一错误码。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotConfiguredError(DataSvcError):
    """WrenAI / 只读库未配置(未对接时的正常态)。"""

    code = ErrorCode.NOT_CONFIGURED


class ValidationError(DataSvcError):
    """SQL 解析失败 / 含 DML·DDL / 表越白名单 / 干跑自纠超限。"""

    code = ErrorCode.VALIDATION_FAILED


class QueryTimeoutError(DataSvcError):
    """执行超 statement_timeout。"""

    code = ErrorCode.TIMEOUT


class AmbiguousFieldError(DataSvcError):
    """字段或口径有歧义,携带澄清项供编排器联动 ask_user。"""

    code = ErrorCode.AMBIGUOUS_FIELD

    def __init__(self, message: str, *, clarifications: list[Clarification]) -> None:
        super().__init__(message)
        self.clarifications = clarifications
