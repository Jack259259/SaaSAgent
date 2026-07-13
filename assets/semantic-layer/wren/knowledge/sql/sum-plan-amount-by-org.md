---
nl: 2026年一季度各组织的资金计划金额合计是多少
sql: |
  SELECT org_id, SUM(plan_amount) AS total_plan_amount
  FROM fund_plan
  WHERE period = '2026Q1'
  GROUP BY org_id
  ORDER BY total_plan_amount DESC
datasource: postgres
tags:
  - seed
  - aggregate
source: seed
---

期间过滤 + 分组聚合的标准形态;period 为字符串精确匹配。
