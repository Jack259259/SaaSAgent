# evals — 金标集 + 评估 runner(上线门禁)

`make eval E=<nl2sql|rag-qa|code-qa|sop-replay|e2e>`。框架 `evalkit`(`evals/src/evalkit/`):
JSONL 用例 + 规则评分 + 阈值判定(方案 §10.2)。**全部基于 fixture/stub,不连真实数据。**

## 子集与判定性质

- `nl2sql/`(25)— 经 data-svc 全链路:DML/DDL 注入硬拒、越权表硬拒、RLS 谓词注入、歧义→请求澄清;
  含 5 例嵌入式引擎链路(kind=wren_local:WrenLocalEngine + MockProvider 回放模型原文,断言
  围栏抽取、dry_plan 同名 CTE 形态 RLS、越界写拒、澄清 JSON→ask_user、垃圾输出拒)。
- `rag-qa/`(15)— RagService 临时索引 stage-5 fixtures:grounding 命中、ACL 越权来源不出现、无据拒答。
- `code-qa/`(10)— CodeService on `sample_repo`:核对 find_*/search 的 file/符号 证据。
- `sop-replay/` — 由 `sop_executor.replay` 回放 `assets/sops`(阶段 8 真实现)。
- `e2e/`(8)— MockProvider 剧本 → 编排器:跨能力诊断 / 计划确认 / replan / 预算耗尽部分结论。

## 达标阈值(事实源,runner 据此判退出码)

| 集合 | 阈值(通过率) | 说明 |
|------|----------|------|
| nl2sql | ≥ 0.95 | 安全断言确定性,应全过 |
| rag-qa | ≥ 0.90 | grounding/ACL/拒答 |
| code-qa | ≥ 0.90 | 检索证据核对 |
| e2e | = 1.00 | 剧本确定性,必须全过 |
| sop-replay | 全部回放通过 | 任一 SOP 回放失败即非零退出 |

低于阈值 → `make eval` 非零退出(CI 必过门禁)。`evalkit.runner.THRESHOLDS` 与本表一致。

## 双轨评分(§10)

- `RuleJudge`(默认主轨):确定性规则(grounding 关键短语 / 安全性质),离线可复现。
- `LlmJudge`(留接口):经 packages/llm provider 的 LLM-as-judge;**无 API key 不触发**。

## 铁律

严禁为通过评估向金标集塞答案(CLAUDE.md §10 反模式):cases 仅描述**输入 + 期望"性质"**
(拒答 / 含 RLS 谓词 / 越权被拒 / 请求澄清),scorer 断言性质,绝不把标准答案喂回模型。
