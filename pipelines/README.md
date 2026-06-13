# pipelines — 资产流水线(CI / 离线作业)

- `code-index/` — 代码索引(tree-sitter 符号图 + 词法检索),阶段 7。
- `ingest/` — 文档摄取到知识库(ACL 元数据,空目录幂等),阶段 5。
- `sop-replay/` — SOP 回放 CI,挂 `make eval E=sop-replay`,阶段 8。

所有管线对空目录幂等空跑(真实数据/代码由人工后续放入 `data/`)。
