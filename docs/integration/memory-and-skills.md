# 记忆与 Skill 对接(方案 §6 / §7)

## 分层记忆(memory-svc)

- 三类:**画像**(profile,结构化偏好/口径)、**情景**(episodic,会话摘要,向量检索)、**经验**(experience,§8.2
  结构:task_signature/适用/有效路径/坑/成本,向量+标签)。
- **隔离(红线 9)**:全部按 `(tenant_id, user_id)` 分区;跨租户/跨用户**搜不到**(存储层即成立,无共享路径)。
- **写入**:先脱敏(手机号/金额打码,接口可换更强规则)→ 重要性门槛(≥阈值 + 去重)→ 存脱敏后内容。
- **来源**:`save_memory` 工具仅写画像类(契约 scope=profile/preference/glossary);**经验仅 reflection-worker**
  经 `MemoryService.record_experience` 录入(9b 反思管道;本阶段仅接口 + 角色闸)。
- **读取**:开场注入画像 + 相关记忆/经验 TopK(各 token 上限);任务中可调 `search_memory`。
- 存储为内存版(进程内,按租户+用户分区);生产换 postgres + 向量库(接口已留)。用户可查看/编辑/删除自己的记忆(治理 TODO)。

## Skill(渐进式披露,§6.2)

- 目录约定:`assets/skills/<name>/SKILL.md` —— YAML frontmatter(`name` / `description` / `triggers`)+ 正文(方法论)。
- 启动构建**索引**(仅 name+description)注入系统提示;编排器判定相关时调 `load_skill(name)` 加载正文。
- 示例:`assets/skills/demo-variance-analysis`(月度差异分析,编排 query_finance_data + search_knowledge,虚构示例)。
- 资产改动走评审;低命中/负收益 Skill 进复审队列(治理 TODO)。

## 开场注入

网关建会话时算 `opening_system_prompt(user_ctx, memory_service, skill_index, query=首条消息)`,经
`build_system_prompt` 注入 Skill 索引 / 记忆 / 经验三段,各段按 token 估算截断(`injection.py` 的 *_CAP)。
