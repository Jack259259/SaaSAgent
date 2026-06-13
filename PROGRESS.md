# PROGRESS —— 阶段进度清单

> 阶段定义与完整提示词:`docs/prompts/stages.md`(事实来源);本文件只做进度勾选与 DoD 摘要。
> 铁律:看不到 `make` 命令真实输出不算完成;阶段结束工作区必须干净;不跳序执行。
> 统一命令中尚未到阶段的(dev / contract-test / eval / sop-validate)打印
> "NOT IMPLEMENTED (see PROGRESS.md)" 并以非零码结束,随对应阶段转为真实现。

- [x] 阶段 0:仓库初始化与工程底座(2026-06-13)—— DoD:`make lint && make test` 真实全绿并贴输出;git status 干净;commit `feat(repo)`。
- [x] 阶段 1:契约层(框架无关的接缝)(2026-06-13)—— DoD:`make lint && make test && make contract-test` 全绿(contract-test 真实现:21 份工具规格 + 信封 user_ctx 负例 + schema 正反例 + 模型↔schema 一致性 + docs 不漂移);commit `feat(contracts)`。
- [x] 阶段 2:LLM 网关 + 编排器薄循环 + SSE 网关(2026-06-13)—— DoD:`make lint && make test` 全绿(含 e2e:SSE 事件序列 tool_call/tool_result_summary/answer_delta/done、无 user_ctx 拒绝 401 + 审计);commit `feat(orchestrator)`。
- [ ] 阶段 3:Plan&Execute + 行内反思 + 基础工具第一批(7 件)—— DoD:`make lint && make test` 全绿(计划/确认暂停恢复/replan/ask_user 集成用例);commit `feat(orchestrator)`。
- [ ] 阶段 4:sandbox-svc(run_analysis 受限沙箱)—— DoD:`make lint && make test` 全绿且红线 11 负例全过(断网/越界读/超时/超内存/import 白名单);commit `feat(sandbox)`。
- [ ] 阶段 5:rag-svc(LightRAG 双库 + ACL 前置过滤)—— DoD:`make lint && make test` 全绿(ACL 负例、引用完整、空目录摄取幂等);commit `feat(rag)`。
- [ ] 阶段 6:data-svc(WrenAI 适配 + SQL 校验层)—— DoD:`make lint && make test` 全绿(DML 拒绝/表白名单/RLS 注入含子查询/自纠路径/LIMIT 包装);commit `feat(data)`。
- [ ] 阶段 7:code-svc(索引管线 + 符号图 + 代码子 Agent)—— DoD:`make lint && make test` 全绿(sample_repo 问答带 evidences、预算超限部分结论);commit `feat(code)`。
- [ ] 阶段 8:sop-executor(确定性状态机 + 回放)—— DoD:`make lint && make test && make sop-validate` 全绿(sop-validate 真实现;demo 闭环:暂停→确认→postconditions;负例不报成功);commit `feat(sop)`。
- [ ] 阶段 9a:memory-svc + Skill 装载 —— DoD:`make lint && make test` 全绿(租户隔离负例、写入门槛、脱敏钩子、Skill 渐进式披露);commit `feat(memory)` / `feat(skills)`。
- [ ] 阶段 9b:scheduler-svc + notify + escalate + reflection-worker —— DoD:`make lint && make test` 全绿(订阅确认流、预算停用、频控、经验评分入库、审计断言);commit `feat(scheduler)` / `feat(reflection)`。
- [ ] 阶段 10:评估套件 + 全链路追踪 + 安全负例收尾 —— DoD:`make lint && make test && make contract-test && make eval E=e2e` 全绿(eval 真实现;tests/security 全过);`docs/acceptance-v0.md` 生成;commit `chore(release)`。
