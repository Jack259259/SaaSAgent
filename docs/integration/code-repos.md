# 代码仓对接(代码检索分析子 Agent)——人工步骤清单

代码检索分析能力(方案 §5.1)对**索引过的代码仓**做问答。真实代码仓本阶段留空,下列步骤人工执行。
对外只暴露 `ask_codebase` 工具(主 Agent 只收结构化结论 + 证据,探索过程不回流——红线 12);
服务对象默认内部研发/支持角色(§9.1),不向租户终端用户暴露源码。

## 1. 投放代码仓

```bash
git clone <repo-url> data/repos/<repo-name>     # 每个仓一个子目录
```
`data/repos/` 除 README 外不入库(`.gitignore: data/**`)。

## 2. 构建符号索引

```bash
uv run code-index --repos-root data/repos --db data/code-index/symbols.db
```
- 支持语言:python / javascript / typescript / java / sql(**best-effort**,精度差异见 `code_svc/languages.py`:
  python 最准,sql 最弱、无调用边)。
- **空目录幂等空跑**;增量按文件 (mtime, size) 跳过未变更、清理已删文件的符号。
- 产物:SQLite 符号库(`data/code-index/symbols.db`,不入库)+ 度中心性 repo map(查询时按 token 预算生成)。

## 3. 增量刷新

代码更新后重跑同一条 `code-index` 命令即增量(未变更文件跳过)。生产可挂 CI webhook 在提交后触发,分钟级生效。

## 4. 词法检索后端(可选 Zoekt)

- 默认:`search_code` 走 **ripgrep 子进程**(仅在索引仓根内检索;rg 不在则纯 Python 兜底)。
- 启用 Zoekt(毫秒级 trigram 检索):取消 `docker-compose.yml` 中 `zoekt` 服务注释并 `docker compose up -d zoekt`,
  回填 `ZOEKT_URL`(如 `http://localhost:6070`);未运行时自动回退 ripgrep,结果结构一致。

## 5. 验证

- 单测(无需真实仓,fixtures/sample_repo):`make test SVC=code-svc`(符号抽取、find_definition/references/callers、
  repo map 度中心性 + token 截断、read_file 越界拒、ripgrep/python 检索一致)。
- 子 Agent 集成:`services/orchestrator/tests/test_ask_codebase_tool.py`("X 被谁调用"→证据、模块问答、预算超限部分结论)。
- 投放真实仓后冒烟:`uv run code-index …` 看 stats;经 ask_codebase 问"函数 X 在哪/谁调用",核对 evidences 的 file:行号。

## 边界(红线 12 / 禁止项)

- code-svc 的检索与文件读取是**受控原语**:只读、**限索引仓根**(`read_file` / ripgrep 经 realpath 前缀校验,越界拒);
  子 Agent 只回**行段 + 结论**,绝不把整文件交给主 Agent 上下文。
- **不上语义向量索引**(§5.1 暂不上,接口预留);概念式查询命中率持续偏低再评估。
