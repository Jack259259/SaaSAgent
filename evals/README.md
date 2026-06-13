# evals — 金标集 + 评估 runner(上线门禁)

`make eval E=<nl2sql|rag-qa|code-qa|sop-replay|e2e>`。runner 与达标阈值在**阶段 10**落地
(本文件届时补全各集阈值)。子集:

- `nl2sql/` — NL→SQL:DML 注入 / 越权表 / RLS 断言 / 歧义触发 ask_user(阶段 6 起填充)。
- `rag-qa/` — 知识问答:含"无据应拒答" + ACL 负例(阶段 5 起)。
- `code-qa/` — 代码问答:基于 sample_repo,核对 evidences(阶段 7 起)。
- `sop-replay/` — SOP 回放,挂 `pipelines/sop-replay`(阶段 8 起)。
- `e2e/` — MockProvider 剧本:跨能力诊断 / 计划确认 / replan / 预算耗尽(阶段 2 起)。

铁律:严禁为通过评估向金标集塞答案(CLAUDE.md §10 反模式)。
