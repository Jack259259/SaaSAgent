# 后端待补清单(内嵌前端对接)

> 前端(`web/`)已按设计契约实现;以下为对接真实后端前需后端补齐的端点/字段。前端均已留 mock 与降级,不阻塞开发。

## A. 文件上传(§12-D2)

- **`POST /files`(multipart)→ `{file_id, filename, mime, size, status}`**:后端暂无此端点。前端经 `fetch('/files')` 上传;mock 模式由 `web/mock/mock-sse.js` 拦截,真实模式 404 → 前端友好提示“后端 /files 待实现(D2)”。
- **`GET /files/{file_id}`**:元数据 / 下载(回看用),待补。
- **`/chat` 接受 `attachments: [file_id, ...]`**:当前 `ChatRequest` 仅 `message` + `page_context`,**无 `attachments` 字段**(pydantic 默认忽略额外键)→ 前端携带的 file_id 不会传达给 Agent。需在 `ChatRequest` 增 `attachments: list[str] | None`,并由编排器按需调 `parse_user_file(file_id)`。

## B. 解析器分批(§12-D3)

后端 `parse_user_file` 当前覆盖 **xlsx / csv / pdf 文本**。按优先级补:

- 第一批:**DOCX、MD、JSON、HTML**(覆盖多数企业文档 / 结构化数据)。
- 次之:ODT、RTF、EPUB。
- 图片(JPEG/PNG/GIF):暂不要求解析,仅上传 + 缩略图,待多模态启用输入。
- 建议:DOCX→python-docx/mammoth、MD/JSON/TXT→直读、HTML→trafilatura、ODT/RTF→pandoc、EPUB→ebooklib。
- 对未支持类型,`parse_user_file` 应返回**明确错误码**;前端据此标注“已上传,解析待后端支持”(现由 mock 的 `parse_supported` 模拟:xlsx/csv/pdf=true)。

## C. SSE 协议字段(W2 投影发现)

- **`citation` 事件未在 `docs/dev/sse-protocol.md` 冻结**:前端按设计 §7 基准实现 CitationList(假定 `{items:[{title,source,ref}]}`)。后端需在协议补 `citation` 事件,或在答案内联引用。
- **`step{index,note}` 无每步状态枚举**:前端按到达顺序投影(index 进行中、前置完成)。如需精确状态,建议 replan 时重发带 `status` 的 steps,或在 `step` 增 `status`。
- **`tool_result_summary{id,tool,summary,workspace_ref}` 无成功/失败、无内容类型/行数**:前端默认 ✓,`error` 事件转 ✗;折叠分档按 `summary` 启发式。建议补 `ok: bool` / `result_kind` / `row_count`,以精确分档与失败标记。
- **恢复语义**:`confirm_request` 用布尔 `confirmation:{confirmed}`,前端把 `options[0]` 映射为确认;**`ask_user` 恢复体 `answers:{...}` 键名未在协议定义**,前端按 `{questionIndex: 选项}` 构造,待后端明确键约定。

## D. 身份(§12-D4)

- 生产应由网关验证短时令牌并服务端构造 `user_ctx`(`agent_gateway/auth.py` 已标 TODO),前端不再注入 `X-User-Ctx`,改走同源 cookie/session。

## E. Skill 管理(W4 前端已实现,以下后端待补)

前端「Skill 管理」(`web/js/skills.js` + `web/mock/mock-skills.js`)已对 mock 联调完成;**真实后端需新增以下端点,均需管理员/内部角色鉴权**(§9.1 角色矩阵;非授权 403)。前端入口已按 user_ctx 角色门控(`canManageSkills`),写操作经统一 http 透传 `X-User-Ctx`。

API(对齐设计 §8.5.4):
- `GET    /skills` → `[{ id, name, description, status(active|draft|review), updated_at }]`
- `GET    /skills/{id}` → `{ id, name, description, content(SKILL.md), status, ... }`
- `POST   /skills` (name, content) → 创建;**入草稿**(status=draft,D5);SKILL.md schema 校验失败返回 **422 + `{ errors:[...] }`**(前端在表单内逐条展示,不静默)
- `PUT    /skills/{id}` (name, content) → 更新;回草稿待审
- `DELETE /skills/{id}` → 删除
- `POST   /skills/{id}/status` (status: active|draft) → 状态变更(发布生效;仅管理员)
- `POST   /skills/upload` (multipart .zip) → 逐条解压入库结果 `{ results:[{ name, ok, status?, reason? }] }`

**`/skills/upload` 安全要求(前端无法保证,必须后端做,红线 7/10)**:
- **zip slip 路径穿越防护**:拒绝 `../` 等逃逸路径,解压目标必须落在隔离目录内。
- **解压炸弹防护**:限制解压后总大小与文件数(建议 **50MB / 500 文件**),超限即拒。
- **结构白名单**:每个 Skill 为一目录,`SKILL.md` 必需 + 可选 `scripts/`、`resources/`;其余结构拒绝。
- **SKILL.md schema 校验**:frontmatter(name/description 等)+ 正文规范。
- **入库策略按 D5**:落**草稿态**(draft),经审核转 active;不让任意上传即时生效(Skill 正文进 LLM 上下文,是提示注入面)。

**治理(后端红线 10)**:`assets/skills/` 的任何改动必须过 schema 校验 + 对应评估回归 + git 版本化与评审后方可合并;写 API 应落入此治理流(草稿 → 审核 → 生效),而非直接改生效库。

## F. 消息反馈(点赞 / 点踩 · 操作栏)

前端「消息操作栏」(`web/js/chat.js`)对模型回复支持**点赞 / 点踩**(互斥 toggle,再点取消)+ 点踩后**可选意见**(≤500 字);vote/意见**持久化于会话历史**(localStorage,刷新不丢)。**反馈上报端点后端待补**:

- **`POST /feedback` → `{ ok: true }`**,请求体 `{ message_id, session_id?, trace_id?, vote: "up"|"down"|null, comment? }`。
  - **当前前端 `feedbackEndpoint=null` → 仅本地暂存**(`localStorage.fp_feedback_queue`),**不发网络请求**(避免对不存在端点 POST 产生控制台错误,亦免脏请求)。端点就绪后将 `feedbackEndpoint` 置 `'/feedback'`:改走网络上报 + 失败回退暂存,登录后可批量回放暂存队列。
  - **`trace_id` 目前 SSE 未暴露**(见 §C):前端暂以 `message_id` + `session_id` 标识;后端若在 `done` 事件 / 响应头暴露 `trace_id`,前端将一并上报以贯穿可观测链路(Langfuse)。
  - 鉴权同 `/chat`(同源 cookie/session 或 `X-User-Ctx`);**按租户隔离存储,反馈数据不跨租户**(红线 9)。意见为用户输入,后端入库前应做长度/注入防护。

## G. 代码仓管理(已实现)+ 安全解压复用

- **`/admin/repos*`(已实现)**:`agent-gateway` 已落地代码仓管理端点(list/clone/upload/delete/update),内部管理员 + 功能开关 `FP_REPO_ADMIN=1` + 主机白名单 `FP_REPO_GIT_HOSTS` + 审计;git/解压/索引硬化见 `services/agent-gateway/src/agent_gateway/repos.py`,UI 见 `web/`「代码仓管理」面板。详见 `docs/integration/code-repos.md §6`。
- **安全解压已就位**:`packages/common/src/common/safe_extract.py`(防 zip-slip/炸弹/符号链接,支持 zip+tar 系)。**§E 的 `/skills/upload` 安全解压可直接复用此模块**,无需再造;后端实现 `/skills/upload` 时调用 `safe_extract(...)` 即满足红线 11/14 的解压安全要求。

## H. 知识库管理(已实现)

- **`/admin/kb/{kb}/*`(已实现)**:`agent-gateway` 已落地知识库管理端点(docs 列举 / upload / download / ingest / ingest status),内部管理员鉴权(`require_kb_admin`)+ IT 设计库细 ACL(仅内部角色,`rag_svc.acl.is_internal`,红线 5/§9.1)+ 写操作审计。实现见 `services/agent-gateway/src/agent_gateway/kb.py`,UI 见 `web/`「知识库管理」面板(`web/js/kb.js`)。详见 `docs/integration/knowledge-management.md`。
  - **ingest 进程内异步**:`asyncio.run(ingest_dir(...))` 后台线程执行(**无子进程 / 无 shell**;kb 取自枚举、src 取自固定映射 → 命令注入面为零),同库串行(运行中再触发 → 409),job 注册表供 `GET .../ingest/status` 轮询。
  - **文档落盘** `data/knowledge/{business|it-design}/`(env `FP_KNOWLEDGE_DIR` 可覆盖);文件名取 basename + 扩展名白名单(`.md/.markdown/.txt/.docx`)+ realpath 父目录校验(防穿越)+ 25MB 上限 + `parse_document` 试解析(损坏即拒)。
- **`.docx` 解析已就位(ingest 路径)**:`rag_svc.chunking.parse_document` 现支持 `.docx`(零依赖 stdlib `zipfile`+`xml.etree`,段落保序 + 表格转 Markdown)。**注意:此为知识库 ingest 路径**;§B 的 `parse_user_file`(聊天附件解析)DOCX 仍待补,可复用 `rag_svc.chunking._docx_to_text`。
- **知识图谱(后端层已实现)**:见 §I。前端「查看知识图谱」按钮当前仍为占位(可视化前端单独成段)。

## I. 知识图谱查询(后端已实现 + 生产化 TODO)

- **`/admin/kb/graph*`(已实现)**:三只读端点(`graph` / `graph/node/{entity_id}` / `graph/search`),
  从 LightRAG 图提取 nodes/edges。鉴权复用 `require_kb_admin` + `it_design` 细 ACL(`is_internal`);
  开关 `FP_KB_GRAPH`(默认开,`=0`→404);节点/边按租户∧标签在 rag-svc 内过滤(红线 5/9)。
  契约见 `docs/integration/knowledge-graph-api.md`;实现 `agent_gateway/kb_graph.py` + `rag_svc/graph.py`。
- **引擎**:`FP_KB_GRAPH_ENGINE` 默认 `mock`(`MockGraphProvider`,虚构 fixture,CI/联调用);生产切
  `lightrag`(`LightRagGraphProvider`,真实图,**不进 CI** —— lightrag 未安装,镜像 `LightRagStore` 范式)。
- **生产化 TODO(投产前接入真实图谱时)**:
  1. **建图**:rag-svc 切真实 `LightRagStore`(`pip install lightrag-hku`)并对 business/it_design ingest
     建图(当前默认 `LocalKnowledgeStore`、未建图 → 真实引擎下图为空)。
  2. **图 ACL 标签级**:LightRAG 图节点/边原生**无 tenant_id/acl_tags**(provenance 仅 source_id/file_path)。
     当前 `LightRagGraphProvider` 用 **(kb, tenant) 分目录物理隔离**(租户级,红线 9)+ **库默认标签**回退
     (标签级 best-effort)。精确标签需:摄取时写入 `file_path` + 维护 `file_path→acl_tags` sidecar
     (由 rag-svc ingest 的 per-doc 元数据构建);`LightRagGraphProvider._tags_for` 已留接入点。
  3. **degree/source/chunk_ref**:真实路径为 best-effort(可能 null),前端需容忍。
- **前端图谱可视化**:`web/` 的「查看知识图谱」交互(节点图渲染、点选下钻、搜索)单独成段实现,
  对接上述契约。
