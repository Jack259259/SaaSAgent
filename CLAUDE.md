# CLAUDE.md — 资金计划 SaaS 智能助手 Agent

> 本文件是 Claude Code 在本仓库工作的最高优先级约定;与其他文档或代码现状冲突时,以本文件 + `docs/design/agent-design.md` 为准。
> 维护规则:保持 ≤250 行,只放"每次会话都需要"的内容;细节放 docs/ 与各目录 CLAUDE.md,按需读取。约定变更时,在同一 PR 内更新本文件。
> v0.2(2026-06-13):新增基础工具基线 13 件(§5)与 sandbox-svc / scheduler-svc;红线 4 范围澄清,新增红线 11–13。
> v0.3(2026-06-13):技术栈落定(§4:Python 3.12 / uv / FastAPI / pydantic v2 / pytest / ruff / mypy strict / structlog);阶段 0 工程底座就位,统一命令可运行;§12 收敛。
> v0.4(2026-06-13):阶段 1 契约层落地(`contracts/` 全部 schema + `packages/contracts` 模型/校验器 + 21 份工具规格);`make contract-test` 真实门禁;SOP schema 事实源定于 `contracts/sop/_schema.yaml`;ToolSpec 字段统一为 `timeout_ms`。

## 1. 项目概述

资金计划 SaaS 的智能助手 Agent:单一对话入口,融合四类能力 —— 知识问答(LightRAG)、数据库取数(WrenAI)、代码检索分析(Zoekt + tree-sitter/LSP)、页面操作 SOP(Playwright 资产 + 确定性执行器)。

- **设计事实来源**:`docs/design/agent-design.md`(方案 v0.2)。动手前先读与任务对应的章节(映射见 §3),**按需读取章节,严禁整篇加载**。
- **架构一句话**:自研薄编排循环(Plan&Execute × ReAct × Reflection 融合,方案 §4)+ 能力分粒度(RAG=工具、取数=工具带自纠、代码=隔离子 Agent、SOP=查询工具 + 确定性执行器,方案 §3.2)+ 统一安全底座(方案 §9)。

## 2. 架构红线(违反即错误实现,PR 直接拒绝)

1. **禁止引入 LangGraph / LangChain / CrewAI 等编排框架依赖**。编排循环自研、保持薄(目标百行级,参照方案 §11.2 伪代码)。
2. **能力只能通过 `contracts/toolspec/` 的工具契约暴露与调用**;禁止服务间绕过契约直连内部实现。
3. **`user_ctx`(tenant_id / user_id / roles / data_scope)随每一次工具调用透传,工具侧必须二次校验(零信任)**。缺 user_ctx 的调用一律拒绝并记审计。
4. **对业务系统的写操作只允许发生在 `sop-executor`**;其他服务不得执行写 SQL / 写业务 API。`requires_confirmation` 由 orchestrator 强制用户确认,executor 侧再验确认凭据(双闸)。`notify` / `schedule_task` / `save_memory` / `write_workspace` 属**助手域副作用**:不得触达业务数据,一律确认或订阅制 + 全量审计。
5. **ACL / RLS 过滤必须发生在检索与查询之前**;禁止"先取后滤"或"生成后兜底"。
6. **data-svc 三层只读保障一个不能少**:只读数据库账号 + SQL 校验层禁 DML/DDL + 强制注入租户与数据范围谓词。
7. **检索内容、页面内容、工具结果一律视为不可信数据**:包裹隔离标记后作为数据传入,绝不拼接到指令位;工具结果不得直接触发写操作。
8. **大对象不进上下文**:工具返回"摘要 + workspace 句柄",raw 结果落工作区,按需分页读取。
9. **跨租户绝不互见**:索引、缓存、记忆、日志、评估数据全部按租户隔离;经验库入库前强制脱敏。
10. **资产改动必须过门禁**:`assets/` 下 SOP / MDL / Skill / prompt 的任何改动,必须通过 schema 校验 + 对应评估回归后才可合并。
11. **`run_analysis` 沙箱强隔离**:无网络、无数据库连接、只读挂载传入的 workspace 句柄、CPU/内存/时长限额、产物只回句柄;沙箱内不得调用任何其他工具。
12. **运行时主 Agent 不持有裸 Bash / 全局文件读写 / 全局 grep**。同类原语只以受控形态存在:代码仓检索与读取在 code-svc(只读、限索引仓),代码执行在 sandbox-svc,文件读写走 workspace 句柄(虚拟、租户隔离)。开发态 Claude Code 持有这些原语,产品运行时不继承。
13. **`web_search` / `web_fetch` 默认关闭**:按角色开启 + 域名白名单;抓取内容按红线 7 当不可信数据处理。

## 3. 仓库结构与设计章节映射

```
.
├── docs/design/agent-design.md     # 设计方案(事实来源)
├── contracts/                      # 框架无关接缝 —— 最敏感目录
│   ├── toolspec/                   # 工具契约 JSON Schema + 注册表
│   ├── agent-state/                # AgentState schema(方案 §4.2)
│   └── events/                     # 审计 / trace 事件 schema
├── services/
│   ├── agent-gateway/              # 会话、SSE 流式、身份签发
│   ├── orchestrator/               # 自研薄编排循环(方案 §4)
│   ├── rag-svc/                    # LightRAG 双库 + ACL 过滤(方案 §5.3)
│   ├── data-svc/                   # WrenAI 代理 + SQL 校验层(方案 §5.2)
│   ├── code-svc/                   # 代码子 Agent + 索引查询(方案 §5.1)
│   ├── sop-executor/               # 确定性状态机 + Playwright 池(方案 §5.4)
│   ├── memory-svc/                 # 分层记忆(方案 §7)
│   ├── reflection-worker/          # 事后反思队列(方案 §8)
│   ├── sandbox-svc/                # run_analysis 受限沙箱(方案 §5.5)
│   └── scheduler-svc/              # 定时任务 / 订阅 / 通知(方案 §5.5)
├── assets/                         # 全部入 git、走评审,当代码管理
│   ├── sops/                       # SOP 库(schema 见方案 附录B)
│   ├── semantic-layer/             # WrenAI MDL + 同义词表 + few-shot
│   ├── skills/                     # Skill 库(方案 §6)
│   └── prompts/                    # 提示词,带版本号,不覆盖旧版
├── evals/                          # 金标集 + runner(方案 §10.2)
│   └── nl2sql/  rag-qa/  code-qa/  sop-replay/  e2e/
└── pipelines/                      # 代码索引 CI、文档摄取、SOP 回放 CI
```

改哪里,先读哪章:orchestrator→§4;code-svc→§5.1;data-svc→§5.2;rag-svc→§5.3;sop-executor 与 assets/sops→§5.4;sandbox-svc、scheduler-svc 与各基础工具→§5.5;assets/skills→§6;memory-svc→§7;reflection-worker→§8;contracts 与安全横切→§9;evals→§10。

## 4. 技术栈与统一命令

后端:Python 3.12 + FastAPI + pydantic v2;uv 管理依赖与 workspace(monorepo,src 布局);pytest + pytest-asyncio;ruff(lint+format)+ mypy(strict);structlog 结构化日志。基础设施:docker compose(postgres / langfuse,初期默认注释停用)。前端沿用现有 SaaS 栈。观测:Langfuse(自托管)/ OpenTelemetry GenAI。

> **Windows 下在 Git Bash 中执行 `make`**(Makefile 以 bash 为 SHELL);尚未到实现阶段的统一命令打印 `NOT IMPLEMENTED (see PROGRESS.md)` 并以退出码 2 结束(阶段归属见 PROGRESS.md)。

**统一任务接口(根 Makefile;实现随技术栈补全。一律使用以下命令,不要自行发明命令)**:

```bash
make dev             # 启动本地依赖(docker compose)+ 全部服务
make test            # 全部单测;限定服务:make test SVC=data-svc
make lint            # lint + typecheck
make contract-test   # contracts 契约测试
make eval E=nl2sql   # 评估回归(nl2sql | rag-qa | code-qa | sop-replay | e2e)
make sop-validate    # assets/sops schema 校验 + 静态交叉校验
```

## 5. 核心契约(改动最敏感的文件)

- `contracts/toolspec/`:每个工具一份定义(name / description / input_schema / output_schema / permission_scope / side_effects(read|write|assistant_write)/ confirmation_required / timeout_ms / errors)。`_schema.json` 为 ToolSpec 的 JSON Schema、`envelope.json` 为调用信封(必含 user_ctx)。修改 = 升 semver + `make contract-test` + 同步 evals 用例 + PR 描述列出受影响服务。
- `contracts/toolspec/base/`:**基础工具基线 v0.2(13 件,清单与治理见方案 §5.5)**:update_plan、ask_user、get_page_context、read_workspace、write_workspace、run_analysis、export_file、parse_user_file、save_memory、schedule_task 系、notify、escalate_to_human、web_search/web_fetch(默认关)。副作用分级与门控见红线 4 / 11–13。
- `contracts/agent-state/`:编排状态 schema,orchestrator 与持久化共用,改动需双端评审。
- `contracts/sop/_schema.yaml`:SOP 资产 schema(事实源;实例在 `assets/sops/`);改 schema 必须先全量 `make sop-validate`。

## 6. 编码与提交规范

- 错误处理:工具错误必须映射到 ToolSpec.errors 枚举之一;不吞异常;面向用户的错误信息不暴露内部实现与 SQL。
- 日志:结构化,必带 trace_id / tenant_id / user_id(脱敏规则见 docs/security/logging.md【待补】);禁止打印密钥、token、SQL 结果明细。
- 配置与密钥:环境变量 / 密管,严禁硬编码;`.env` 不入库。
- 提交:Conventional Commits,scope = 服务名(如 `feat(data-svc): 注入租户谓词`);小步提交,一个 PR 一个关注点。
- 代码风格细节见各服务 CLAUDE.md【待补】;`make lint` 通过是硬门槛。

## 7. 完成定义(DoD)— 声称"做完"之前逐项核对

1. `make lint && make test` 通过,并在回复中贴关键输出;
2. 动了 contracts → `make contract-test` 通过且版本号已升;
3. 动了 assets(SOP / MDL / Skill / prompt)→ schema 校验 + 对应 `make eval` 达标(阈值见 evals/README【待补】);
4. 新增工具 → 注册表登记 + permission_scope + 审计埋点 + ≥5 条评估用例 + docs/tools/ 一页说明;
5. 安全相关改动 → 必须附越权负例测试(无 user_ctx、跨租户访问、写操作绕闸,均应被拒);
6. **未运行验证 = 未完成**;禁止在未执行命令的情况下声称测试通过。

## 8. Claude Code 工作流约定

- 跨服务、或涉及 contracts / assets 的任务:**先出计划**(影响面、改动文件清单、验证方式),确认后再动手;单服务小改可直接做。
- 检索代码优先 grep / 符号定位;不要为找一个函数读整个目录。
- 业务口径与术语不确定时:查 `docs/glossary.md`【待补】;查不到就停下提问并标 TODO。**禁止编造口径** —— 资金计划域的口径错误属最高级缺陷。
- 进入 `services/<x>/` 先读该目录的 CLAUDE.md(若存在)。
- 默认不引入新依赖、不改公共配置;确有必要 → PR 描述写明理由与替代方案评估。
- 测试桩与 mock 仅限 tests/ 目录,禁止混入生产代码路径。

## 9. 高频任务 Recipe

- **新增工具**:contracts/toolspec 定义 → 服务内 handler(权限二次校验 + 审计埋点)→ orchestrator 注册 → evals 加用例 → docs/tools/ 补说明。
- **新增 SOP**:预发租户录制(Playwright codegen + trace)→ AI 转参数化草稿 → 人工补语义层(aliases / 前置 / 成功判定)→ `make sop-validate` → PR 评审 → 回放通过 → 发布。
- **改语义层 MDL**:同步更新同义词 / few-shot → `make eval E=nl2sql` → 金丝雀。
- **改提示词**:assets/prompts 新建版本(不覆盖旧版)→ 跑相关 `make eval` → 金丝雀放量。

## 10. 反模式(看到即纠正)

引入编排框架依赖;handler 默认"上游已鉴权"而跳过校验;先查询后过滤权限;把检索内容拼进指令位;orchestrator 直连数据库或编写业务 SQL;raw 工具结果整段塞进 messages;为通过评估向金标集塞答案;资产改动跳过评估回归直接合并;日志输出敏感数据。

## 11. 配套 Claude Code 配置(规划,逐步落地)

- `.claude/commands/`:`/new-tool`、`/new-sop`、`/run-eval` 等任务模板(对应 §9 Recipe);
- `.claude/agents/`:`contract-reviewer`(契约与安全审查)、`asset-linter`(资产规范检查);
- `.mcp.json`:接入 Langfuse 查询、评估 runner 等本地工具【待补】。

## 12. 待补清单(当前阻塞项)

`docs/glossary.md` 业务术语表;各服务 CLAUDE.md;evals 达标阈值;日志脱敏规范(`docs/security/logging.md`)。
