---
nl: 存在失败流水的资金计划有哪些
sql: |
  SELECT plan_id, org_id, period
  FROM fund_plan
  WHERE plan_id IN (SELECT plan_id FROM exec_flow WHERE status = 'FAILED')
datasource: postgres
tags:
  - seed
  - subquery
source: seed
---

status 枚举:SUCCESS / FAILED / PENDING。
