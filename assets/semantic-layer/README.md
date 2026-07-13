# assets/semantic-layer — 取数语义层

- `tables.yaml` — **校验层事实源**:表白名单 + 每表 RLS 租户列(红线 6;data-svc/validator.py 消费)。
- `wren/` — **Wren 语义层项目**(嵌入式 WrenAI):MDL 模型 + 业务规则 + few-shot,
  供 NL2SQL 生成与 dry_plan 方言转换;维护约定与真实表替换指引见 `wren/README.md`。

两者必须保持一致(模型↔白名单双向对应),由 `services/data-svc/tests/test_wren_assets.py` 在 CI 强制。
改动任一侧 → `make wren-build` + `make test SVC=data-svc` + `make eval E=nl2sql`(CLAUDE.md §9 / 红线 10)。
