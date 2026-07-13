# 业务规则与 SQL 方言约束(NL2SQL 生成用;资产,走评审)

## 业务口径(虚构 3 表示例;真实口径由数据团队维护,禁止编造)

- **执行率** = 执行金额 / 计划金额(`exec_amount / NULLIF(plan_amount, 0)`,除零保护必须用 NULLIF)。
- **期间(period)** 格式为 `YYYYQn`(如 `2026Q1`)或 `YYYYMM`,字符串精确匹配,不做日期运算。
- 金额单位一律为**元**(DECIMAL);币种在 `currency` 列,聚合跨币种金额前应按币种分组。
- 执行流水状态 `status` 枚举:`SUCCESS` / `FAILED` / `PENDING`。
- 计划与科目、流水的关联键均为 `plan_id`。

## SQL 方言约束(目标库:华为 GaussDB,按 PostgreSQL 兼容子集生成)

只使用 ANSI SQL 与 PostgreSQL 的公共子集,**禁止**以下 PostgreSQL 专有写法:

- `::` 类型转换 —— 用 `CAST(x AS DECIMAL(18, 4))`;
- `DISTINCT ON` —— 用 `GROUP BY` 或窗口函数改写;
- `ILIKE` —— 用 `LOWER(col) LIKE LOWER('%...%')`;
- `LATERAL`、数组/JSONB 操作符(`@>`、`->`、`->>` 等)、`RETURNING`、`generate_series`。

其他约定:

- 日期字面量写 `DATE '2026-01-01'`;日期区间用 `>= 下界 AND < 上界(开区间)`。
- 除法先 `CAST` 成 DECIMAL 再除,避免整型截断。
- 只允许单条 `SELECT`;任何写操作(INSERT/UPDATE/DELETE/DDL)一律禁止。
- **不要**在 SQL 里添加 `tenant_id` 过滤 —— 租户隔离由系统在校验层自动注入。
