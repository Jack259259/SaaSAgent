# WrenAI(NL2SQL)对接 —— 嵌入式路线(已落地)

> v2(2026-07-14):原「部署 WrenAI 服务 + HTTP 对接」方案作废 —— WrenAI 官方已把 Docker 托管栈
> (wren-ui / wren-ai-service,`/api/v1/generate_sql`)标记为 **GenBI Classic 并 sunset(不再有安全修复)**。
> 现行路线:**嵌入式**接入 pip 包 `wrenai`(v0.13,Rust/DataFusion 引擎 + 文件化 YAML 语义层)。
> 旧 `WrenAdapter`(HTTP `POST /v1/ask`)保留为 legacy 后备,不再对官方栈适配。

## 架构与分工

```
问句 + user_ctx
  → WrenLocalEngine(data_svc/wren_local.py,FP_NL2SQL_ENGINE=wren_local)
      ├─ 提示词:assets/prompts/nl2sql/v1.md + 语义层资产(schema/规则/few-shot)→ system 位
      ├─ SQL 生成:本仓统一 LLM 通道(packages/llm Provider,config/llm.yml;不建第二条通道)
      └─ wren 校验/转换:WrenEngine.dry_plan(strict_mode 拒 manifest 外表/数据读取函数;
         fallback=False 语法错即抛,错误信息回流内部自纠 ≤1 次;空连接=纯变换,无 DB)
  → SqlValidator(不动,红线 6):只读断言 → 白名单 → RLS 注入 → LIMIT
  → 执行器(FP_DATA_EXECUTOR=user_func):DataFrameFunctionExecutor(run_sql)
      —— explain 干跑失败回流外层自纠(≤2 次);execute 转 DataFrame → 结果
```

要点:**SQL 由我方 LLM 生成,wren 只提供语义层 + 校验 + 方言转换**(这是新版 WrenAI 官方形态);
安全不依赖任何一环的提示词 —— 校验层永远在线。

## 启用步骤

```bash
uv sync --all-packages --extra wren   # 装 wrenai(红线 1 门禁已过:依赖树无 langchain/langgraph/crewai)
make wren-build                       # 语义层校验+编译(改 assets/semantic-layer/wren 后必跑)
```

`config/app.yml`:

```yaml
FP_NL2SQL_ENGINE: "wren_local"   # 留空=legacy WrenAdapter(NOT_CONFIGURED 现状)
FP_DATA_EXECUTOR: "user_func"    # 留空=PostgresExecutor(需 DB_DSN_READONLY)
```

再配好 `config/llm.yml`(真实 LLM,非 dev_stub)即可端到端。

## 语义层与 few-shot(资产,红线 10)

事实源 `assets/semantic-layer/wren/`(模型/关系/业务规则/few-shot),维护约定、
与 `tables.yaml` 白名单的一致性铁律、**真实业务表替换指引**见该目录 README。
一致性由 `services/data-svc/tests/test_wren_assets.py` 在 CI 强制。
改动流程:改资产 → `make wren-build` → `make test SVC=data-svc` → `make eval E=nl2sql` → PR。

## GaussDB 口径(重要)

- 目标库为华为 GaussDB,按 **PostgreSQL 兼容子集**处理:MDL `data_source: postgres`,
  dry_plan 产出 postgres 方言;提示词与 `knowledge/rules/general.md` 约束 GaussDB 安全子集
  (禁 `::`、DISTINCT ON、ILIKE、LATERAL、数组/JSONB、RETURNING、generate_series)。
- **待确认**:GaussDB 实例的兼容模式(PG / ORA / MySQL)。非 PG 模式需参数化 dry_plan 目标方言
  与校验层 `_DIALECT`,并调整 few-shot(增量 PR)。真实库联调前先确认。

## 用户执行代码接入点(唯一替换点)

`services/data-svc/src/data_svc/user_executor.py` 的 **`run_sql(sql: str) -> pandas.DataFrame`**:
把函数体换成你的 GaussDB 连接/查询代码即可(签名不变,当前为 DuckDB+种子数据占位实现)。
你的实现须:**只读账号** + 会话 `statement_timeout` + 原样执行传入 SQL(会收到 `EXPLAIN <sql>`
形式的干跑请求)。进阶:也可自行实现完整 `ReadOnlyExecutor` 协议(`explain`/`execute`)并在
`agent-gateway/deps.py` 的 `_data_executor()` 接入。

## 已知边界与自纠分层

- wren `dry_plan` **不校验列存在性**(实测,fallback 两种模式皆然):坏列名由外层
  `executor.explain`(EXPLAIN 干跑)捕获并回流自纠 —— 内层纠语法/表级错,外层纠执行错,正交。
- wren 侧真实 `dry_run` 需数据库连接,不使用;MDL 级校验由 `dry_plan`(strict)承担。
- `wrenai` 版本锁 `>=0.13,<0.14`(Beta);wren API 面收敛在 `wren_local.py` 的
  `WrenPlanner` 接缝,升级只动该文件 + 跑 `test_wren_integration.py`(真实 dry_plan 输出
  过校验层的回归锚点,装了 extra 才执行)。
- Windows 开发注意:`wren` console-script 在非 ASCII 仓路径不可用,统一走
  `scripts/wren_cli.py`(make wren-build 已封装);`target/mdl.json` 落盘编码随系统
  locale(wren 上游未指定 utf-8),运行时用内存构建不受影响。

## 边界(本次明确不做)

真实 GaussDB 连接实现(`run_sql` 函数体归用户);Classic 托管栈;`memory.store` 线上
few-shot 回补(需红线 9 租户治理,后续项);真实业务表 MDL(仅模板+指引);LanceDB 向量
召回(3 表全量上下文足够,`memory` extra 未装);LLM 判歧增强(现靠提示词约定澄清 JSON)。

## 验证

- 离线(不需 wrenai/真实 LLM):`make test SVC=data-svc`(引擎 MockProvider+FakePlanner、
  执行适配、问句→数据全链路)+ `make eval E=nl2sql`(25 例含 5 例 wren_local 链路)。
- 真实 wren(装 extra 后自动生效):`test_wren_integration.py` —— dry_plan 输出过白名单+RLS、
  strict 拒未知表/read_csv、语法错带信息抛出。
- 手动冒烟(config/llm.yml 已配真实 LLM):`FP_NL2SQL_ENGINE=wren_local` +
  `FP_DATA_EXECUTOR=user_func` 起服务,问「2026年一季度各组织的资金计划金额合计」,
  应返回带 `tenant_id = '<本租户>'` 的最终 SQL 与占位种子数据结果;
  问「执行率怎么算」应触发澄清(ask_user)。
- legacy 路径回归:`WrenAdapter` 原测试保留(httpx MockTransport)。
