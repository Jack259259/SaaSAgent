# PROGRESS —— 阶段进度清单

> 阶段定义与完整提示词:`docs/prompts/stages.md`(事实来源);本文件只做进度勾选与 DoD 摘要。
> 铁律:看不到 `make` 命令真实输出不算完成;阶段结束工作区必须干净;不跳序执行。
> 统一命令中尚未到阶段的(dev / contract-test / eval / sop-validate)打印
> "NOT IMPLEMENTED (see PROGRESS.md)" 并以非零码结束,随对应阶段转为真实现。

- [x] 阶段 0:仓库初始化与工程底座(2026-06-13)—— DoD:`make lint && make test` 真实全绿并贴输出;git status 干净;commit `feat(repo)`。
- [x] 阶段 1:契约层(框架无关的接缝)(2026-06-13)—— DoD:`make lint && make test && make contract-test` 全绿(contract-test 真实现:21 份工具规格 + 信封 user_ctx 负例 + schema 正反例 + 模型↔schema 一致性 + docs 不漂移);commit `feat(contracts)`。
- [x] 阶段 2:LLM 网关 + 编排器薄循环 + SSE 网关(2026-06-13)—— DoD:`make lint && make test` 全绿(含 e2e:SSE 事件序列 tool_call/tool_result_summary/answer_delta/done、无 user_ctx 拒绝 401 + 审计);commit `feat(orchestrator)`。
- [x] 阶段 3:Plan&Execute + 行内反思 + 基础工具第一批(7 件)(2026-06-13)—— DoD:`make lint && make test` 全绿(计划→并行→失败→replan→完成、写步骤 confirm 暂停/恢复、ask_user 往返、反思重试≤2、5 件 base 工具、跨租户会话拒绝);commit `feat(orchestrator)`。
- [x] 阶段 4:sandbox-svc(run_analysis 受限沙箱)(2026-06-13)—— DoD:`make lint && make test` 全绿且红线 11 负例全过(断网/越界读/超时/import 白名单跨平台;超内存 POSIX/CI;正例 CSV→PNG;run_analysis 越权被拒);commit `feat(sandbox)`。
- [x] 阶段 5:rag-svc(双库 RAG + 检索前 ACL 过滤 + 引用)(2026-06-14)—— DoD:`make lint && make test` 全绿(检索前 ACL 负例 tenant 看不到 internal、it_design 仅内部、引用完整、空目录摄取幂等 + hash 增量、Embedder 网关);commit `feat(rag)`。
- [x] 阶段 6:data-svc(WrenAI 适配 + SQL 校验层 + RLS)(2026-06-14)—— DoD:`make lint && make test` 全绿(DML/DDL 拒绝、表白名单、RLS 注入含子查询/CTE、行级隔离、自纠路径、LIMIT 包装、AMBIGUOUS→ask_user 集成、NOT_CONFIGURED);commit `feat(data)`。
- [x] 阶段 7:code-svc(索引管线 + 符号图 + 代码子 Agent)(2026-06-14)—— DoD:`make lint && make test` 全绿(tree-sitter 符号抽取、find_definition/references/callers、repo map 度中心性 + token 截断、ripgrep/python 检索一致、read_file 越界拒、空目录幂等;子 Agent sample_repo 问答带 evidences、预算超限部分结论);commit `feat(code)`。
- [x] 阶段 8:sop-executor(确定性状态机 + 回放)(2026-06-14)—— DoD:`make lint && make test && make sop-validate` 全绿(sop-validate 真实现:schema + 占位符/confirm/api·ui 交叉校验;demo 闭环:执行→暂停→确认→完成→postconditions 回查;postcondition 失败/拒绝确认/precondition/步骤失败负例不报成功;Playwright 驱动 demo 页;run_sop 经编排器 tool_confirm 双闸;make eval E=sop-replay 接入);commit `feat(sop)`。
- [x] 阶段 9a:memory-svc + Skill 装载(2026-06-15)—— DoD:`make lint && make test && make contract-test` 全绿(租户/用户隔离负例、写入门槛+去重、脱敏钩子、经验仅 reflection 可录、Skill 索引注入+按需 load_skill、开场注入 MockProvider 捕获 system 不超限;新增 search_memory/load_skill 契约 23 份 + docgen);commit `feat(memory)` / `feat(skills)`。
- [x] 阶段 9b:scheduler-svc + notify + escalate + reflection-worker(2026-06-15)—— DoD:`make lint && make test` 全绿(订阅 confirm 流、max_runs/max_cost+连续失败停用、notify 频控、escalate 工单+脱敏、经验评分过阈入库/低分不入、助手域写审计断言);commit `feat(scheduler)` / `feat(reflection)`。
- [ ] 阶段 10:评估套件 + 全链路追踪 + 安全负例收尾 —— DoD:`make lint && make test && make contract-test && make eval E=e2e` 全绿(eval 真实现;tests/security 全过);`docs/acceptance-v0.md` 生成;commit `chore(release)`。
