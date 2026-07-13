---
nl: 执行率低于50%的资金计划清单
sql: |
  SELECT plan_id, org_id, period, plan_amount, exec_amount
  FROM fund_plan
  WHERE plan_amount > 0
    AND CAST(exec_amount AS DECIMAL(18, 4)) / plan_amount < 0.5
datasource: postgres
tags:
  - seed
  - metric
source: seed
---
