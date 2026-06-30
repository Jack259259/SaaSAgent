# 知识文档人工上传规范(rag-svc)

知识文档由**人工上传**到 `data/knowledge/{business,it_design}/`,再运行 `ingest` 构建索引。
**真实业务文档不入库**(`data/` 除 README 外被 .gitignore 忽略)。

> 也可经内嵌前端「知识库管理」面板(内部管理员)上传 + 一键入库,免手工命令;
> 端点与安全见 `docs/integration/knowledge-management.md`。CLI 仍是租户私有/子目录语料的入口。

## 目录与命名

- 业务知识 → `data/knowledge/business/`;IT 设计文档 → `data/knowledge/it-design/`(对应 kb=`it_design`)。
- 文件名用有意义的英文/拼音 + 扩展名;**当前支持 `.md` / `.markdown` / `.txt` / `.docx`**(pdf 解析器待接入,见 chunking.py TODO)。
- **`.docx`**:零依赖解析(stdlib OOXML),抽取段落(保序)+ 表格(转 Markdown);无 front-matter,元数据取库默认。复杂排版(图片/文本框/批注)忽略。损坏文件在 ingest 时跳过、不中断整批。

## front-matter 元数据格式(放文件顶部)

```markdown
---
source: 业务手册/执行率口径        # 来源(展示在引用里)
version: "1.0"                   # 版本
effective_date: "2026-01-01"     # 生效日期(YYYY-MM-DD)
acl_tags: [public]               # ACL 标签(见下)
tenant_id: t_acme                # 可选:租户私有归属;缺省=全局知识(见下"租户维度")
---
正文……
```

支持的子集:`key: 标量` 与 `key: [a, b]`(引号可选)。无 front-matter 时:source=相对路径、
acl_tags 取库默认(business→`public`,it_design→`internal`)、tenant_id 缺省为全局(None)。

## acl_tags 取值约定(红线 5)

| 标签 | 含义 | 谁能检索到 |
|------|------|-----------|
| `public` | 全租户公开 | 所有角色 |
| `tenant` | 仅租户内部 | 租户用户/管理员 + 内部角色 |
| `internal` | 仅内部 | internal_support / internal_dev 等内部角色 |

- **KB 级**:`it_design` 库**仅内部角色**可查(§9.1),无权角色根本不查该库(§9.3 物理隔离)。
- **tag 级**:角色授予标签集 ∩ chunk.acl_tags ≠ ∅ 才可见;过滤发生在**检索前**(LocalKnowledgeStore 候选阶段),绝不生成后兜底。

### 租户维度(红线 9,跨租户绝不互见)

- **缺省全局**:不写 `tenant_id` → 该片段为全局知识,对所有租户可见(适合 SaaS 产品/领域通用文档)。
- **租户私有**:写 `tenant_id: <租户ID>`(或摄取时 `--tenant <租户ID>`)→ 该片段**仅本租户**可检索到,
  其他租户即便角色标签匹配也**根本不进候选**(与标签同为检索前过滤)。front-matter 的 `tenant_id` 覆盖 CLI 的 `--tenant`。
- **铁律**:租户私有/敏感的"业务数据本身"应走 data-svc(库内 RLS),**不要**塞进知识库;知识库放的是文档化知识。

## 上传后执行的命令

```bash
# 业务库(全局知识)
uv run ingest --kb business   --src data/knowledge/business
# IT 设计库
uv run ingest --kb it_design  --src data/knowledge/it-design
# 某租户私有业务文档(整目录归该租户;片段仅该租户可见)
uv run ingest --kb business   --src data/knowledge/tenants/t_acme --tenant t_acme
```

- **空目录**:无文件 → 幂等空跑(退出 0),这是人工上传前的常态。
- **增量**:按文件 sha256 跳过未变更;改动后重跑即增量更新。
- 索引默认写到 `data/knowledge/.index/{kb}/index.json`(网关检索从此加载;`.index` 不入库)。

## 生产引擎(LightRagStore)

默认引擎为 `LocalKnowledgeStore`(本地文件 + 词法哈希向量,确定性)。生产可切 `LightRagStore`
(真 LightRAG,可选依赖 `lightrag-hku`):其 embedding_func / llm_model_func **经 packages/llm 网关**
(不直连厂商 SDK)。注意 LightRAG **无元数据候选过滤**,检索前 ACL 仍须 RagService 入口层负责
(按库/标签分区入库);存储后端可选本地文件或 postgres(pgvector)。

**开启真实知识图谱**(独立于上面的检索引擎,见 `backend-gaps.md` §I):① 装可选依赖
`uv sync --all-packages --extra lightrag`(pin `lightrag-hku==1.5.4`,默认/CI 不装)+ ② 真实 LLM
(`config/llm.yml` 非 `dev_stub`/非 Mock)+ ③ `config/app.yml` 设 `FP_KB_GRAPH_ENGINE=lightrag`(+ `FP_KB_GRAPH≠0`)。
本地起:`uv sync --extra lightrag` 后 `uv run --no-sync python -m uvicorn agent_gateway.app:app …`
(`make dev` 会 sync 掉 extra,故用 `--no-sync`)。建图经 `POST /admin/kb/{kb}/ingest`,前端「查看知识图谱」面板展示。
