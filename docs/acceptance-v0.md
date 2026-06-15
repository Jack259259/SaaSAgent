# 资金计划 Agent —— v0 验收(红线 1–13 自检)

> 日期:2026-06-15。范围:阶段 0–10 全部完成。v0 为**离线自洽闭环**(全部 fixture/stub,
> 不连真实库/知识/代码仓/业务写)。本文逐条核对 CLAUDE.md §2 架构红线,给代码位置与守护测试。
> 事实源:CLAUDE.md §2 + docs/design/agent-design.md §9。

## DoD 结论

| 门禁 | 结果 |
|------|------|
| `make lint`(ruff format + ruff check + mypy --strict,188 源文件) | ✅ 全绿 |
| `make test`(全仓 pytest) | ✅ 242 passed, 1 skipped(POSIX-only 沙箱内存用例在 Windows 跳过) |
| `make contract-test`(契约 41 用例) | ✅ 全绿 |
| `make eval E=nl2sql\|rag-qa\|code-qa\|e2e` | ✅ 20/20、15/15、10/10、8/8 均达阈(阈值见 evals/README.md) |
| `make eval E=sop-replay` | ✅ 回放全过 |
| `tests/security`(安全负例总套件) | ✅ 12/12 |
| CI(.github/workflows/ci.yml) | 增 `eval-e2e` + `security-negatives` 为必过门禁 |

## 红线逐条自检

**红线 1 —— 禁编排框架依赖,薄循环自研。** 全仓无 langchain / langgraph / crewai 依赖(各
`pyproject.toml` 仅 fastapi/pydantic/structlog 等);编排循环自研于 `services/orchestrator/src/orchestrator/loop.py`
(Plan&Execute × ReAct × Reflection 融合)。✅

**红线 2 —— 能力只经 contracts/toolspec 暴露调用。** 注册表从契约装载并据此暴露 ToolDef:
`orchestrator/registry.py:70-82`(`register_from_contracts` → `load_toolspecs`)、`registry.py:106-111`
(`tool_defs` 由 spec 生成)。代码子 Agent 的内部工具是实现细节,唯一对外契约是 `ask_codebase`
(`orchestrator/tools/codebase.py`)。✅

**红线 3 —— user_ctx 透传 + 工具侧二次校验(零信任);缺 user_ctx 拒 + 审计。**
`ToolContext.user_ctx` 随每次调用透传(`tool_context.py`);`registry.py:121` 调用前 `checker.check(ctx.user_ctx, spec)`;
`permissions.py:17-21` `assert_user_ctx(None)` 即拒;契约信封强制 user_ctx(`contracts/validator.py:56`)。
守护:`tests/security/test_sec_no_user_ctx.py`(全工具矩阵无 user_ctx 被契约拒;越权调用产生
`result_status=denied / error_code=NO_PERMISSION` 审计)。✅

**红线 4 —— 写仅 sop-executor + 确认双闸;助手域副作用确认/订阅 + 审计,不触业务数据。**
`orchestrator/tools/sop.py:32-37,64-70`:run_sop 命中 confirm 步即返回 `ToolConfirmation`,编排器
`loop.py` 暂停发 `ConfirmRequestEvent`(第一闸),executor 在 resume 内复验(第二闸);助手域
schedule/notify/escalate 均确认/订阅制 + structlog 审计且不触业务数据(`orchestrator/tools/proactive.py`)。
守护:`tests/security/test_sec_write_gate.py`(未确认不写、拒绝确认不写、编排器强制确认)。✅

**红线 5 —— ACL/RLS 必须在检索/查询之前。** rag 检索前过滤候选再打分:
`rag-svc/store.py:68-71`(`candidates = [c for c in ... if visible(c)]` 早于打分);取数前注入租户谓词:
`data-svc/validator.py:79-94`。守护:`rag-svc/tests/test_acl.py`、`evals/nl2sql`(require_rls)。✅

**红线 6 —— data-svc 三层只读。** ① 只读账号:`data-svc/executor.py`(PostgresExecutor 只读 DSN,
未配置即 NOT_CONFIGURED);② 禁 DML/DDL:`validator.py:68`(含 CTE 内 DELETE,`validator.py:24` 说明);
③ 强制租户谓词:`validator.py:93-94`(白名单 + tenant_column 注入)。校验失败硬拒不自纠
(`data-svc/service.py:65`)。守护:`data-svc/tests/test_validator.py`、`evals/nl2sql`。✅

**红线 7 —— 检索/工具结果=不可信数据,不拼指令位、不直接触发写。** 工具结果以 `ToolResultBlock`
进入用户态数据消息(`loop.py` `tool_results_message`),系统提示由 `build_system_prompt` 固定生成、
不拼检索内容;写工具仍受确认闸。守护:`tests/security/test_sec_prompt_injection.py`(注入文本只在
数据位、绝不进任何 system 提示;被诱导调用 run_sop 仍被确认闸拦下,不自动写)。✅

**红线 8 —— 大对象不进上下文:摘要 + workspace 句柄,raw 落工作区分页读。**
`ToolOutcome(summary, raw)`(`registry.py:32-42`);编排器把 summary 入消息、raw 经
`workspace.put` 落工作区返回句柄(`loop.py` `_plan_phase`/`_execute_step`);`read_workspace` 分页读
(`orchestrator/workspace.py`)。守护:`orchestrator/tests/test_workspace.py`。✅

**红线 9 —— 跨租户绝不互见;经验入库脱敏。** rag 租户维度过滤(`rag-svc/acl.py:44-46`)、
memory 按 `(tenant_id,user_id)` 限定(`memory-svc/service.py:125-138`)、会话归属校验
(`SessionStore` → `SessionAccessError`);经验入库经 `BasicRedactor` 脱敏(`memory-svc/service.py:68-69`)。
守护:`tests/security/test_sec_cross_tenant.py`(rag/memory/会话三维跨租户拒;经验写受角色闸)。✅

**红线 10 —— 资产改动过门禁。** SOP/MDL/Skill/prompt 改动须过 schema 校验 + 评估回归:
`make sop-validate`(`Makefile:73`)、`make eval`(`Makefile:61`)、`pipelines/sop-replay`。✅

**红线 11 —— run_analysis 沙箱强隔离。** 无网络(`sandbox-svc/_harness.py:56-64` socket 拦截)、
import 白名单 + 剔除逃逸 stdlib(`_harness.py:23,39`)、只读挂载工作区句柄(`runner.py:43`)、
CPU/内存/时长限额(`runner.py:53,88,119`)、产物只回句柄、沙箱内不调其他工具
(`orchestrator/tools/analysis.py:3-4` handler 不放宽隔离)。守护:sandbox-svc 负例(断网/越界读/超时/
超内存/import 白名单)。✅

**红线 12 —— 运行时主 Agent 无裸 Bash/全局文件读写/全局 grep。** `base_tool_handlers()`
(`orchestrator/tools/__init__.py:36-43`)仅 get_page_context/read_workspace/write_workspace/export_file/
parse_user_file/run_analysis —— 无 bash/grep/全局 fs。同类原语仅受控形态:代码检索在 code-svc(只读、
限索引仓),执行在 sandbox-svc,文件读写走 workspace 句柄。✅

**红线 13 —— web_search/web_fetch 默认关。** `contracts/toolspec/base/web_search.yaml:25`
(`enabled_by_default: false`)+ 描述标注"角色 + 域名白名单开启;内容按不可信数据处理";二者均未进
`base_tool_handlers`(默认不注册=默认关)。✅

## 可观测与评估

- **全链路 trace**:`packages/llm/tracing.py`(`Tracer`/`LocalTracer`/`get_tracer`/`bind_trace`/
  `current_trace_id`);provider 与 `ToolRegistry.invoke` 埋 span,trace_id 经 contextvar/ctx 贯穿
  provider→工具→子 Agent;未配置 `LANGFUSE_*` 静默降级为本地 structlog span。守护:
  `orchestrator/tests/test_tracing_spans.py`(同一 trace_id 贯穿 provider/主 Agent 工具/子 Agent 工具)。
- **评估**:`evals/`(evalkit + 5 集),规则评分为主轨 + LLM-judge 留接口;阈值集中 `evals/README.md`;
  cases 仅描述输入 + 期望"性质",不向金标集塞答案(CLAUDE.md §10 反模式)。

## v0 边界与投产前接入项

v0 全程离线 stub。投产真实接入(均已留契约/适配位)见 CLAUDE.md §12:① 数据库对接(WrenAI + 只读库 +
真实 MDL)② 知识上传(LightRAG 后端)③ 代码仓放入(真实只读仓索引)④ 生产沙箱(ContainerRunner)
⑤ 审批引擎对接(工单 + 业务写 API)。
