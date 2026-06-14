# pipelines/ingest — 知识文档摄取

实现位于 `services/rag-svc/src/rag_svc/ingest.py`(rag-svc 是 workspace 包,可导入可测;
`pipelines/` 非 Python 包,故管线逻辑落服务内,此处仅作入口指引)。

CLI(控制台脚本 `ingest`,见 rag-svc 的 `[project.scripts]`):

```bash
uv run ingest --kb business  --src data/knowledge/business
uv run ingest --kb it_design --src data/knowledge/it-design
```

行为:解析 md(front-matter 元数据 + 正文分块)→ 向量化(packages/llm 网关)→ 写本地索引;
**空目录幂等空跑**;按文件 sha256 **跳过未变更**。上传规范与 acl_tags 约定见
`docs/integration/knowledge-upload.md`。
