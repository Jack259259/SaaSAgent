# contracts/events — 审计 / trace 事件 schema

审计事件字段:who/user_ctx、tool、args_digest(脱敏)、result_status、trace_id、ts(方案 §9.2)。
日志禁止打印密钥、token、SQL 结果明细(CLAUDE.md §6)。

`audit.json` 在**阶段 1**落地。
