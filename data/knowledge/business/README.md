# data/knowledge/business — 业务知识库上传区(人工)

此目录由**人工上传**业务知识文档(口径、制度、流程等),供 rag-svc 的 business 库摄取。

- **真实数据不入库**:除本 README 外,本目录内容被 `.gitignore` 忽略,不进 git。
- 上传规范(命名、front-matter 元数据、acl_tags 取值)见 `docs/integration/knowledge-upload.md`(阶段 5 补)。
- 上传后运行 `pipelines/ingest`(阶段 5)摄取;空目录摄取幂等空跑。
