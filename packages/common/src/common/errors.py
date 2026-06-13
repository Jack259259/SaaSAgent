"""统一错误枚举(阶段 0 空壳)。

§6:工具错误必须映射到 ToolSpec.errors 枚举之一;不吞异常;
面向用户的错误信息不暴露内部实现与 SQL。

跨服务通用错误(如 NO_PERMISSION / NOT_CONFIGURED / TIMEOUT / VALIDATION_FAILED)
的枚举定义随契约层(阶段 1)落地于此。
"""
