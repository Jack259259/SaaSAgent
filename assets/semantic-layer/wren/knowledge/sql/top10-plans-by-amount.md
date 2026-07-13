---
nl: 计划金额最大的前十个资金计划
sql: |
  SELECT plan_id, org_id, period, plan_amount
  FROM fund_plan
  ORDER BY plan_amount DESC
  LIMIT 10
datasource: postgres
tags:
  - seed
  - topn
source: seed
---
