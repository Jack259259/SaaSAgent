# Wren 语义层项目(嵌入式 WrenAI,NL2SQL 事实源之一)

data-svc 的 `WrenLocalEngine` 惰性装载本目录(`wren.context.build_manifest`),用于:
schema 上下文入提示词、few-shot 召回、MDL 校验(strict)与 dry_plan 方言转换。
对接总览见 `docs/integration/wrenai.md`。

## 目录

- `wren_project.yml` — 项目元数据;`data_source: postgres` 为 GaussDB 的 PG 兼容口径。
- `models/<表名>/metadata.yml` — 每表一个模型;`table_reference` 用**裸表名**(catalog/schema 留空)。
- `relationships.yml` — 模型关联(JOIN 语义)。
- `knowledge/rules/*.md` — 业务口径 + 方言约束(全量进 NL2SQL 提示词)。
- `knowledge/sql/*.md` — few-shot 问句→SQL 对(YAML frontmatter:`nl` / `sql`;全量进提示词)。
- `target/`、`.wren/` — 编译/索引产物,**不入库**(.gitignore),`make wren-build` 重建。

## 一致性铁律(CI 由 services/data-svc/tests/test_wren_assets.py 守护)

1. 模型集合与 `../tables.yaml` 白名单**双向一致**(每模型有白名单项、每白名单表有模型);
2. 模型 `table_reference.table` = 模型名 = 裸表名(与校验层"末段匹配"口径一致);
3. 模型列 ⊆ `tables.yaml` 该表列,且必须包含该表的 `rls.tenant_column` 列;
4. few-shot 的 SQL:单条 SELECT、只引用白名单表、**禁止出现 tenant_id 过滤**(租户隔离由校验层注入,不教模型写)。

## 改动流程(红线 10)

改本目录任何文件 → `make wren-build`(schema 校验+编译)→ `make test SVC=data-svc`
→ `make eval E=nl2sql` 达标 → PR 评审。few-shot 增补同流程。

## 真实业务表替换指引

1. 数据团队按 `models/fund_plan/metadata.yml` 模板为每张真实表建 `models/<表>/metadata.yml`
   (列、类型、口径描述写进 `properties.description`);
2. 同步在 `../tables.yaml` 登记白名单 + `rls.tenant_column`(两边一致性由 CI 强制);
3. `knowledge/rules/` 补真实业务口径(指标定义、期间格式、枚举值);`knowledge/sql/` 换真实 few-shot;
4. 若真实表在固定 schema 下,可在 `table_reference.schema` 填写 —— 校验层白名单按表名末段匹配,不受影响;
5. 跑一遍「改动流程」;真实库联调前先与用户确认 **GaussDB 兼容模式(PG/ORA/MySQL)**。
