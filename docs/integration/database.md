# 取数库对接(只读账号 + RLS)——人工步骤清单

data-svc 取数走**只读账号 + 校验层(禁 DML/DDL)+ 强制租户谓词注入**(红线 6)。真实库本阶段不连接;
下列步骤在对接时人工执行。校验层(`data_svc/validator.py`)无论是否连库都生效,**无"测试态放行"开关**。

## 1. 建只读账号(PostgreSQL 示例)

```sql
CREATE ROLE zijin_readonly LOGIN PASSWORD '<强随机>';
GRANT CONNECT ON DATABASE <db> TO zijin_readonly;
GRANT USAGE ON SCHEMA <schema> TO zijin_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA <schema> TO zijin_readonly;       -- 仅 SELECT
ALTER DEFAULT PRIVILEGES IN SCHEMA <schema> GRANT SELECT ON TABLES TO zijin_readonly;
-- 不授予任何 INSERT/UPDATE/DELETE/DDL;不授予对系统表的额外权限。
```

`PostgresExecutor` 另在会话内 `SET TRANSACTION READ ONLY` + `SET statement_timeout`(双保险)。

## 2. 登记白名单与 RLS(语义层资产)

编辑 `assets/semantic-layer/tables.yaml`(走评审,红线 10):
- `tables.<表名>.columns`:列清单;
- `tables.<表名>.rls.tenant_column`:该表的租户列(配了才会被注入租户谓词;不配=仅受白名单约束、无行级隔离)。
- **不在册的表一律拒查**(含 `pg_catalog` 等系统表)。
本阶段为 3 张虚构示例表(fund_plan / plan_subject / exec_flow)。真实表上线需逐表评审 RLS 配置。

## 3. 回填环境变量(勿入库,走密管)

```bash
export DB_DSN_READONLY="postgresql://zijin_readonly:<pw>@<host>:5432/<db>"
```
未设置时取数工具返回 `NOT_CONFIGURED`(正常未对接态)。

## 4. 验证

- 单测(无需真实库,DuckDB 替身):`make test SVC=data-svc`。重点断言:DML/DDL 拒、白名单外拒、
  RLS 谓词存在(含子查询/CTE)、行级隔离、自纠路径、LIMIT 包装。
- 连库冒烟(对接后):用只读账号执行一条 `SELECT`,确认注入了 `tenant_id = '<本租户>'` 且只回本租户行;
  尝试 `UPDATE`/`DROP` 应被账号权限与校验层双重拒绝。

## RLS 注入要点(红线 6 / 红线 5)

校验层用 sqlglot 遍历**每个 SELECT 作用域**,凡引用带 RLS 配置的基表即把 `<别名>.<租户列> = '<tenant_id>'`
AND-进该作用域 WHERE——**子查询与 CTE 定义各为独立作用域,均被覆盖**。tenant_id 取自 `user_ctx`(零信任,
不信上游)。data_scope(组织/期间等更细粒度)为后续扩展点,接口已预留。
