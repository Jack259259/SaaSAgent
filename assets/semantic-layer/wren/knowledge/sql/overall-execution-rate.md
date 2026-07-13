---
nl: 2026年一季度整体的计划执行率是多少
sql: |
  SELECT CAST(SUM(exec_amount) AS DECIMAL(18, 4)) / NULLIF(SUM(plan_amount), 0) AS execution_rate
  FROM fund_plan
  WHERE period = '2026Q1'
datasource: postgres
tags:
  - seed
  - metric
source: seed
---

执行率口径:执行金额/计划金额;NULLIF 防除零,CAST 防整型截断(禁用 :: 转换)。
