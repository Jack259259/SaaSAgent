---
nl: 2026年1月的执行流水明细
sql: |
  SELECT flow_id, plan_id, exec_date, amount, status
  FROM exec_flow
  WHERE exec_date >= DATE '2026-01-01' AND exec_date < DATE '2026-02-01'
  ORDER BY exec_date
datasource: postgres
tags:
  - seed
  - daterange
source: seed
---

日期区间:DATE 字面量 + 左闭右开;不用 generate_series / 日期函数方言。
