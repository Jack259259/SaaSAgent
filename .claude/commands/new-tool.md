---
description: 新增一个工具(契约 → handler → 注册 → evals → 文档),按 CLAUDE.md §9 / DoD §7.4 执行
argument-hint: <tool_name> [所属服务,如 data-svc]
---

# 新增工具:$ARGUMENTS

按 CLAUDE.md §9 Recipe 与 DoD §7 第 4/5 条逐步执行。**先出计划,确认后再动手**(跨 contracts 任务)。

## 步骤

1. **契约先行** — 在 `contracts/toolspec/<domain|base>/<tool_name>.yaml` 定义工具:
   `name / description / input_schema / output_schema / permission_scope / side_effects(read|write|assistant_write)/ confirmation_required / timeout_ms / errors`。
   - 写操作(side_effects=write)`confirmation_required` 必为 true,且只能落在 `sop-executor`(红线 4);助手域副作用按红线 4 确认或订阅制。
   - 升 ToolSpec semver;`errors` 用既有枚举,新枚举同步 `packages/common/errors`。

2. **服务内 handler** — 在所属服务实现 handler:
   - **入口二次校验 user_ctx 与 permission_scope**(红线 3,零信任,不得假设上游已鉴权);
   - 权限不通过抛 `NO_PERMISSION` 并发审计事件;
   - 检索/页面/工具结果按红线 7 当不可信数据;大对象走"摘要 + workspace 句柄"(红线 8);
   - 错误映射到 ToolSpec.errors,不吞异常,面向用户信息不暴露内部实现/SQL(§6)。

3. **审计埋点** — 每次调用发 `contracts/events/audit` 事件(trace_id / tenant_id / user_id,脱敏)。

4. **注册** — 在 orchestrator ToolRegistry 登记,绑定 handler。

5. **评估用例** — `evals/` 对应集新增 **≥5 条**用例,含越权负例(无 user_ctx / 跨租户 / 写绕闸应被拒,DoD §7.5)。

6. **文档** — `docs/tools/<tool_name>.md` 一页说明(用途、参数、副作用、权限范围、错误)。

## 验收(DoD)

- `make contract-test` 通过且版本号已升;
- `make lint && make test` 全绿(贴真实输出);
- 安全负例测试存在且通过;
- PR 描述列出受影响服务。
