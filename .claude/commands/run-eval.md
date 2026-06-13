---
description: 跑一个评估集并核对阈值(make eval E=<set>),按 CLAUDE.md §9 / §10 执行
argument-hint: <nl2sql|rag-qa|code-qa|sop-replay|e2e>
allowed-tools: Bash(make eval:*), Read, Grep
---

# 运行评估:$ARGUMENTS

## 步骤

1. **运行** — 执行 `make eval E=$ARGUMENTS`,贴出**完整真实输出**。
   - 若评估 runner 尚未实现(阶段 10 前),该命令会打印 `NOT IMPLEMENTED (see PROGRESS.md)` 并以退出码 2 结束 —— 这是预期的,如实说明当前阶段不可跑。

2. **核对阈值** — 对照 `evals/README.md` 中该集的达标阈值判断通过/未通过;贴出关键指标。

3. **失败处置** — 未达标时:
   - **先定位根因**(读相关用例与被测代码),不要猜;
   - 给出最小修复方案并说明为什么是根因;
   - **严禁**为通过评估向金标集塞答案、放宽断言、跳过用例(CLAUDE.md §10 反模式)。

4. **资产相关** — 若本次涉及 assets(MDL / prompt / SOP / skill)改动,确认已过对应门禁(红线 10):
   schema 校验 + 该评估集回归达标后方可合并。

> 金标集是质量地基:它衡量系统,不被系统反向优化。
