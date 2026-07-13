---
nl: 计划 P001 下各科目的金额分布
sql: |
  SELECT subject_code, subject_name, amount
  FROM plan_subject
  WHERE plan_id = 'P001'
  ORDER BY amount DESC
datasource: postgres
tags:
  - seed
source: seed
---
