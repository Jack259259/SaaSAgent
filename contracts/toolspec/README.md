# contracts/toolspec — 工具契约(最敏感目录)

能力只能通过这里的工具契约暴露与调用(红线 2);服务间禁止绕过契约直连内部实现。

**一工具一份定义**,字段:`name / description / input_schema / output_schema /
permission_scope / side_effects / confirmation_required / timeout / errors`(示例见方案 §11.3)。

修改契约 = 升 semver + `make contract-test` + 同步 evals 用例 + PR 描述列出受影响服务(CLAUDE.md §5)。

- `_schema.json`(ToolSpec JSON Schema)、`envelope.json`(调用信封,必含 user_ctx)、
  `domain/`(5 件领域工具)、`base/`(13 件基础工具)—— **均在阶段 1 落地**。
- 副作用分级与门控:read | write | assistant_write,见红线 4 / 11–13。
