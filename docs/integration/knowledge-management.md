# 知识库管理(agent-gateway /admin/kb)

内嵌前端「知识库管理」面板的后端实现:内部管理员维护两个知识库(`business` / `it_design`)的文档
——**上传 → 入库(ingest)→ 下载**。镜像既有「代码仓管理」(`docs/integration/code-repos.md`)形态。
**本段不含知识图谱**(前端「查看知识图谱」为占位 + TODO,后续段实现)。

实现:`services/agent-gateway/src/agent_gateway/kb.py`(ops)+ `app.py`(端点)+ `auth.py`(鉴权);
前端 `web/js/kb.js` + `web/mock/mock-kb.js`。

## 端点(均需内部管理员鉴权 `require_kb_admin`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/admin/kb/{kb}/docs` | 列文档:`[{name,size,mtime,indexed}]`(`indexed`=是否已入库) |
| POST | `/admin/kb/{kb}/upload` | 上传 `.md/.markdown/.txt/.docx`(multipart `file`) |
| GET  | `/admin/kb/{kb}/docs/{name}/download` | 下载原文件 |
| POST | `/admin/kb/{kb}/ingest` | 触发后台入库,返回 `{task_id,status:"running"}` |
| GET  | `/admin/kb/{kb}/ingest/status` | 查询入库状态:`running\|done\|failed\|idle` |

`kb ∈ {business, it_design}`(限枚举,非法 → `404 INVALID_KB`)。

## 鉴权与 ACL(红线 3 / 5 / 9)

- **`require_kb_admin`**(`auth.py`):缺 `X-User-Ctx` → 401;非内部管理员角色
  (`_KB_ADMIN_ROLES = {admin, kb_admin, internal, internal_support, internal_dev}`)→ 403 + denied 审计。
  不设功能开关(无子进程、低风险;repos 的 `FP_REPO_ADMIN` 是为收口 git 子进程攻击面)。
- **IT 设计库细 ACL**:`it_design` 的所有端点叠加 `rag_svc.acl.is_internal(user_ctx)`,非内部角色 → 403
  (§9.1;与检索侧 `kb_allowed` 同口径)。前端 IT 页签亦仅内部角色可见(双保险)。
- 写操作(upload / ingest / download)全量审计(`emit_audit`,tool=`kb_admin:<action>`;不记文件名原文)。

## 安全

- **ingest 无命令注入面**:`ingest` 经**进程内** `asyncio.run(ingest_dir(kb=..., src=..., store_dir=...))`,
  **无 subprocess / 无 shell**;`kb` 取自枚举,`src` 取自固定映射(`KB_DIRS`),无任何用户可控的路径/argv。
  后台线程执行,job 注册表(`_jobs` + 锁)供状态轮询;**同库串行**(运行中再触发 → `409 INGEST_RUNNING`,
  避免并发重建索引竞态)。
- **路径穿越防护**:文件名取 `Path(name).name`(去目录成分)+ 拒 `..`/分隔符/空 + 扩展名白名单
  (`.md/.markdown/.txt/.docx`)+ realpath 父目录校验(必须落在 kb 目录内)+ 长度上限。
- **类型/大小/解析校验**:扩展名 + MIME 软白名单 + 25MB 上限 + 上传即用 `parse_document` 试解析
  (损坏 docx / 非 UTF-8 文本即 `400 INVALID_INPUT`,胜过仅看 MIME)。
- **前端不解析、不解压**(红线 14):docx 解析在后端;列表/错误以 `x-text` 渲染(不可信数据不进指令位)。

## 目录与配置

- 文档落 `data/knowledge/{business|it-design}/`(注意 `it_design` 库目录名为连字符 `it-design`)。
- 索引 `data/knowledge/.index/{kb}/index.json`(`indexed` 判定读其 `file_hashes` 键)。
- 环境变量 `FP_KNOWLEDGE_DIR` 覆盖知识根目录(测试/部署用)。
- 重新 ingest 后,下一次 `/chat` 经 `RagService.from_dir`(每请求重载)自动生效,无缓存需失效。

## 范围与边界

- UI 管理 kb 目录**顶层**文档;**租户私有 / 子目录语料仍走 CLI**(`ingest --tenant`,见
  `docs/integration/knowledge-upload.md`)。
- front-matter(`acl_tags` / `tenant_id` / `version` 等)经文件内容声明;docx 无 front-matter,
  元数据取库默认(business→`public`,it_design→`internal`)。
- 逐文档「入库时间戳」未单独存(索引仅存 `file_hashes`);列表以**文件修改时间 + indexed 状态**呈现,
  kb 级最近入库时间由 ingest job 的 `started_at/finished_at` 给出。
