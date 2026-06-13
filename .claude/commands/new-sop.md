---
description: 新增一个 SOP(录制 → 参数化 → 语义层 → 校验 → 回放 → 发布),按 CLAUDE.md §9 执行
argument-hint: <sop_id,如 demo.create-item>
---

# 新增 SOP:$ARGUMENTS

按 CLAUDE.md §9 Recipe 与红线 4 / 10 执行。SOP 资产入 git、走评审、可回放(资产即代码)。

## 步骤

1. **录制** — 在预发租户用 Playwright codegen + trace 录制目标操作。**不得在真实生产租户录制。**

2. **AI 转参数化草稿** — 将录制转为 `assets/sops/<sop_id>.yaml` 草稿;字段以方案附录 B / `contracts/sop/_schema.yaml` 为准:
   `preconditions / inputs / api / ui.steps / postconditions / on_failure / meta`。
   - 模板占位符 `{{var}}` 必须闭合且在 `inputs` 中有定义;
   - 含写操作的步骤标 `requires_confirmation`(红线 4:执行期由 executor 再验确认凭据,双闸);
   - `api` 与 `ui` 至少其一存在。

3. **人工补语义层** — 补 `aliases`(供 find_sop 检索)、业务前置条件、成功判定(postconditions)。

4. **静态校验** — `make sop-validate`:schema 校验 + 交叉校验(占位符闭合、confirm 标记一致、api/ui 存在性)。

5. **评审** — PR 评审(资产改动必过门禁,红线 10)。

6. **回放** — `make eval E=sop-replay` 在 demo/预发回放通过(暂停→确认→postconditions 全过;失败即失败,不报成功)。

7. **发布** — 回放通过后合并发布。

## 验收(DoD)

- `make sop-validate` 通过;
- `make eval E=sop-replay` 达标;
- `make lint && make test` 全绿(贴真实输出)。

> 禁止:让 LLM 参与执行期决策(执行器是确定性状态机);跳过 postconditions。
