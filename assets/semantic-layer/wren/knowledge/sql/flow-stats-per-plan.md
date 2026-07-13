---
nl: 每个资金计划的执行流水笔数和执行金额合计
sql: |
  SELECT p.plan_id, COUNT(f.flow_id) AS flow_count, COALESCE(SUM(f.amount), 0) AS exec_total
  FROM fund_plan p
  LEFT JOIN exec_flow f ON f.plan_id = p.plan_id
  GROUP BY p.plan_id
datasource: postgres
tags:
  - seed
  - join
source: seed
---

两表 JOIN 的关联键是 plan_id(见 relationships.yml)。
