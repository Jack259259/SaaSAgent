# SOP 资产编写与对接(方案 §5.4 / 附录 B)

## 生产线(录制为主、语义为辅、回放保鲜)

1. 预发租户用 Playwright codegen 录制 + trace(含网络捕获);
2. AI 转参数化 SOP 草稿:role/testid 定位、具体值泛化为 `{{参数}}`、观测接口落 `api` 块;
3. 人工补语义层:`name` / `aliases` / `preconditions` / `postconditions` / `requires_confirmation`;
4. `make sop-validate`(schema + 静态交叉校验)→ PR 评审 → 回放通过(`make eval E=sop-replay`)→ 发布入 `assets/sops/`。

schema 事实源:`contracts/sop/_schema.yaml`。实例放 `assets/sops/*.yaml`(走门禁,红线 10)。

## 字段与约束(sop-validate 强制)

- 字段:`id / name / description / aliases / preconditions / inputs / api | ui / postconditions / on_failure / meta`。
- **占位符**:`api.body` / `ui.value` / `postconditions` 中的 `{{name}}` 必须闭合,且 name 在 `inputs.key`
  或某 `api.calls[].capture` 输出名中有定义。
- **confirm 一致性**:写操作 SOP `requires_confirmation: true`,且 `ui` 至少一个 `confirm: true` 步(反之亦然)。
- **api 与 ui 至少其一**;flow 风格 `{}` 内含中文逗号的值请加引号(避免 YAML 误拆)。
- `postconditions.verify`(api + expect)是**可执行回查**:回查失败即整体失败,**绝不报成功**(红线)。

## 执行语义(确定性状态机,执行期零 LLM)

- 流程:preconditions(权限核验)→ requires_confirmation 则 confirm 步暂停(经网关 confirm_request,红线 4 双闸)
  → 执行(**优先 api**,无 api 走 Playwright)→ postconditions 回查 → succeeded/failed。
- 失败即停、不跳步;按 `on_failure[].when` 匹配给 `hint`;`meta` / `side_effects` 决定可否重入。
- 执行身份 = 发起用户短时令牌(当前桩 `mint_user_token`);业务 API 经 `BUSINESS_API_URL`(未配置即调用失败→run 失败)。

## 校验与回放命令

```bash
make sop-validate           # schema + 交叉校验
make eval E=sop-replay      # 回放全量(失败标 <id>.stale)
```
