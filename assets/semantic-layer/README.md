# assets/semantic-layer — WrenAI 语义层

MDL + 同义词表 + few-shot;表白名单 `tables.yaml`(RLS 注入按表配置,红线 6)。
改 MDL 需同步同义词 / few-shot 并跑 `make eval E=nl2sql`(CLAUDE.md §9)。实现见阶段 6。
