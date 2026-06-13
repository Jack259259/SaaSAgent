# SSE 事件协议(/chat)

> 前端依赖此协议,**字段须稳定**。新增事件类型向后兼容;改字段需同步前端与本文件。
> 编排器事件定义见 `services/orchestrator/src/orchestrator/events.py`。

## 传输

`POST /chat` 返回 `Content-Type: text/event-stream`。每个事件一帧:

```
event: <type>
data: <single-line JSON>

```

(帧之间空行分隔。)请求头 `X-User-Ctx` 必填(JSON 的 user_ctx,红线 3);可选 `X-Trace-Id`。
请求体:`{"message": "...", "page_context": {...}?}`。

## 事件类型

| event | data 字段 | 说明 |
|-------|----------|------|
| `plan` | `version:int`, `steps:[{id,goal,capability_hint,depends_on,status,needs_confirmation}]` | 计划生成/更新(阶段 3 起;字段已冻结) |
| `step` | `index:int`, `note:str` | 一轮含工具调用前的推理摘要(截断 ≤200 字) |
| `tool_call` | `id:str`, `tool:str`, `arguments:object` | 工具调用发起(按顺序) |
| `tool_result_summary` | `id:str`, `tool:str`, `summary:str`, `workspace_ref:str` | 工具完成:**仅摘要 + 句柄**(红线 8),raw 落工作区,按句柄分页读取 |
| `confirm_request` | `id:str`, `prompt:str`, `options:[str]` | 写操作确认暂停(红线 4);本段流随后结束,回执见下 |
| `ask_user` | `id:str`, `questions:[{question, options}]` | 结构化澄清(≤3 问);本段流随后结束,回执见下 |
| `answer_delta` | `text:str` | 最终回答分段 |
| `done` | `stop_reason:str`, `used_steps:int` | 结束。`stop_reason ∈ {end_turn, completed, budget_exhausted, no_progress}` |
| `error` | `code:str`, `message:str` | 错误(message 不暴露内部实现 / SQL,§6) |

## 暂停与恢复(Plan&Execute,阶段 3)

- `/chat` 与 `/chat/confirm` 的响应头均带 **`X-Session-Id`**;前端用它发回执。
- 遇 `confirm_request`(写步骤)或 `ask_user` 时,**本段 SSE 流结束**(不发 `done`),会话状态在服务端保存。
- 恢复:`POST /chat/confirm`,body `{"session_id": "...", "confirmation": {"confirmed": true}?, "answers": {...}?}`
  → 返回**续传的 SSE 段**,直至下一次暂停或 `done`。confirm 用 `confirmation`,ask_user 用 `answers`。
- 会话按 tenant/user 隔离:`/chat/confirm` 的 `X-User-Ctx` 与会话归属不符 → **403**;会话不存在 → **404**(红线 3/9)。

## 鉴权失败(非 SSE)

- 缺 `X-User-Ctx` → **401**;`X-User-Ctx` 非合法 user_ctx → **403**。两者均产生 denied 审计事件。

## 示例帧序列(调用一次工具后作答)

```
event: step
data: {"index": 0, "note": "我来回显一下"}

event: tool_call
data: {"id": "c1", "tool": "echo_tool", "arguments": {"text": "hi"}}

event: tool_result_summary
data: {"id": "c1", "tool": "echo_tool", "summary": "echoed: hi", "workspace_ref": "ws://echo_tool/1"}

event: answer_delta
data: {"text": "结果是 hi"}

event: done
data: {"stop_reason": "end_turn", "used_steps": 1}
```
