# WrenAI(NL2SQL)对接——人工步骤清单

NL→SQL 由 WrenAI 生成,**我方校验层兜底**(红线 6:WrenAI 生成的 SQL 一律过只读断言 + 白名单 +
RLS 注入 + LIMIT 后才执行,绝不直接信任)。真实 WrenAI 本阶段不连接。

## 1. 部署 WrenAI 服务

参考官方仓库 `https://github.com/Canner/WrenAI`(本机镜像:`Agent源码收集/WrenAI/WrenAI-20260614`)。
取得 wren-ai-service 的 HTTP 入口地址(下文记为 `WREN_API_URL`)。

## 2. 灌语义层(MDL)

WrenAI 侧建模(表→业务对象、指标口径、维度、同义词、few-shot 问句-SQL 对)。我方 `tables.yaml` 的
白名单/RLS 与 WrenAI 的 MDL 需保持一致:WrenAI 能引用的表必须都在我方白名单内,否则生成的 SQL 会被校验层拒。

## 3. 回填环境变量

```bash
export WREN_API_URL="http://<wren-host>:<port>"
```
未设置时 `WrenAdapter` 返回 `NOT_CONFIGURED`(正常未对接态)。

## 4. 适配器契约(WrenAdapter)

本阶段 `WrenAdapter` 以最小契约对接(`docs` 与实现保持同步,确切端点在对接时核定):
- 请求:`POST {WREN_API_URL}/v1/ask`,body `{question, tenant_id, prior_error?}`;
- 响应:`{sql}`(直接给 SQL)或 `{clarifications:[{field,question,options}]}`(字段/口径歧义)。
- WrenAI 真实流程为**异步 ask + 轮询结果**;若采用,需在 `WrenAdapter` 内实现"建 ask→轮询 status=finished→取 sql",
  对外接口(`NL2SQLEngine.generate`)不变。
- `prior_error` 用于自纠:校验通过但 EXPLAIN 干跑失败时,带错误回传让 WrenAI 重生成(≤2 次)。

## 5. 验证

- 单测(无需真实服务,StubEngine + httpx MockTransport):`make test SVC=data-svc`(覆盖解析 SQL/澄清、
  NOT_CONFIGURED、自纠序列)。
- 集成(orchestrator):`AMBIGUOUS_FIELD → ask_user → 二次取数`链路见
  `services/orchestrator/tests/test_query_finance_data_tool.py`。
- 连服务冒烟(对接后):一条简单问句应返回可执行 SQL;一条含歧义口径的问句应返回 clarifications。
