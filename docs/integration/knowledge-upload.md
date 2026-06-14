# 知识文档人工上传规范(rag-svc)

知识文档由**人工上传**到 `data/knowledge/{business,it_design}/`,再运行 `ingest` 构建索引。
**真实业务文档不入库**(`data/` 除 README 外被 .gitignore 忽略)。

## 目录与命名

- 业务知识 → `data/knowledge/business/`;IT 设计文档 → `data/knowledge/it-design/`(对应 kb=`it_design`)。
- 文件名用有意义的英文/拼音 + 扩展名;**当前支持 `.md` / `.markdown` / `.txt`**(docx/pdf 解析器待接入,见 chunking.py TODO)。

## front-matter 元数据格式(放文件顶部)

```markdown
---
source: 业务手册/执行率口径        # 来源(展示在引用里)
version: "1.0"                   # 版本
effective_date: "2026-01-01"     # 生效日期(YYYY-MM-DD)
acl_tags: [public]               # ACL 标签(见下)
---
正文……
```

支持的子集:`key: 标量` 与 `key: [a, b]`(引号可选)。无 front-matter 时:source=相对路径、
acl_tags 取库默认(business→`public`,it_design→`internal`)。

## acl_tags 取值约定(红线 5)

| 标签 | 含义 | 谁能检索到 |
|------|------|-----------|
| `public` | 全租户公开 | 所有角色 |
| `tenant` | 仅租户内部 | 租户用户/管理员 + 内部角色 |
| `internal` | 仅内部 | internal_support / internal_dev 等内部角色 |

- **KB 级**:`it_design` 库**仅内部角色**可查(§9.1),无权角色根本不查该库(§9.3 物理隔离)。
- **tag 级**:角色授予标签集 ∩ chunk.acl_tags ≠ ∅ 才可见;过滤发生在**检索前**(LocalKnowledgeStore 候选阶段),绝不生成后兜底。

## 上传后执行的命令

```bash
# 业务库
uv run ingest --kb business   --src data/knowledge/business
# IT 设计库
uv run ingest --kb it_design  --src data/knowledge/it-design
```

- **空目录**:无文件 → 幂等空跑(退出 0),这是人工上传前的常态。
- **增量**:按文件 sha256 跳过未变更;改动后重跑即增量更新。
- 索引默认写到 `data/knowledge/.index/{kb}/index.json`(网关检索从此加载;`.index` 不入库)。

## 生产引擎(LightRagStore)

默认引擎为 `LocalKnowledgeStore`(本地文件 + 词法哈希向量,确定性)。生产可切 `LightRagStore`
(真 LightRAG,`pip install lightrag-hku`):其 embedding_func / llm_model_func **经 packages/llm 网关**
(不直连厂商 SDK)。注意 LightRAG **无元数据候选过滤**,检索前 ACL 仍须 RagService 入口层负责
(按库/标签分区入库);存储后端可选本地文件或 postgres(pgvector)。
